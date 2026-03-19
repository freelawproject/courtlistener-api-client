# Remote MCP Server Deployment Proposal

## Current State

The CourtListener MCP server runs locally via `courtlistener-mcp` (stdio
transport). Users must:

1. Have Python 3.10+ installed
2. Run `pip install courtlistener-api-client[mcp]`
3. Set `COURTLISTENER_API_TOKEN` in their environment
4. Configure their MCP client (Claude Desktop, Cursor, etc.) to launch the process

This works but creates friction — especially for non-technical users or those
unfamiliar with Python packaging.

## Goal

Deploy a **remote MCP server** so users can connect by adding a single URL to
their MCP client config. No local Python install, no pip, no env vars.

---

## Three-Stage Deployment Plan

### Stage 1: Streamable HTTP + Token Passthrough ✅ IMPLEMENTED

Ship a remote-capable server with the simplest auth that works: clients pass
their CourtListener API token via the `Authorization: Token <token>` header.

**What was built:**
- Dual-transport `server.py` (`--transport stdio|streamable-http`)
- `AuthMiddleware` extracts the token from the `Authorization` header and
  stores it in a `contextvars.ContextVar`
- `MCPTool.get_client()` reads the token from: HTTP header → session dict →
  `COURTLISTENER_API_TOKEN` env var (in that priority)
- All 12 API-calling tools updated to pass session context
- `/health` endpoint for load balancer probes
- Dockerfile for containerized deployment
- `uvicorn` and `starlette` added to `[mcp]` optional dependencies

**Client config (Stage 1):**
```json
{
  "mcpServers": {
    "courtlistener": {
      "url": "https://mcp.courtlistener.com/mcp",
      "headers": {
        "Authorization": "Token your-cl-api-token"
      }
    }
  }
}
```

### Stage 2: Staging OAuth with Mock CL Django App

Stand up a **tiny Django app** that mimics CourtListener's auth system and
acts as an OAuth 2.1 authorization server. This lets us build and test the
full OAuth flow with no risk to real CL infrastructure.

**Why a staging OAuth app:**
- Practice adding OAuth to a CL-like Django stack (same user model,
  same `django-oauth-toolkit`)
- Define the exact scopes and claims the MCP server needs — this becomes
  the spec CL implements against
- Test the MCP SDK's `token_verifier` / `AuthSettings` integration against
  a real OAuth server (known rough edges: SDK issues #750, #1063, #1414)
- End-to-end test the browser-based OAuth consent flow that remote MCP
  clients use (Claude Desktop, Cursor, etc.)
- Explicitly disposable — delete when CL ships real OAuth

**What the staging Django app needs:**
- Django + `django-oauth-toolkit` (DOT)
- Same user model pattern as CL (username + API token)
- OAuth authorization / token / introspection endpoints
- A minimal consent screen
- Runs as a service in the same k8s namespace as the MCP server

**What changes on the MCP server:**
- Add SDK-native OAuth support via `token_verifier` parameter
- Add `AuthSettings` with the staging app as the `issuer_url`
- Keep header passthrough as a fallback for non-OAuth clients
- Tool code stays identical — same `request_api_token` contextvar

**Staging app scope (intentionally minimal):**
```
staging-oauth-app/
├── manage.py
├── Dockerfile
├── k8s/
│   ├── deployment.yaml
│   └── service.yaml
└── oauth_staging/
    ├── settings.py      # Django + DOT config
    ├── urls.py           # OAuth endpoints
    ├── models.py         # User + API token model
    └── views.py          # Consent screen
```

### Stage 3: Real CourtListener OAuth

Once CL adds OAuth support (using the spec defined in Stage 2):
- Point `issuer_url` from the staging app to CL's real OAuth endpoints
- Remove the staging Django app
- This should be a **config change, not a code change**

**End-state client config:**
```json
{
  "mcpServers": {
    "courtlistener": {
      "url": "https://mcp.courtlistener.com/mcp"
    }
  }
}
```

No tokens in config. User clicks "authorize" in their MCP client, logs into
CL in their browser, grants consent, done.

---

## Deployment: Kubernetes

The MCP server and staging OAuth app deploy to the existing Free Law Project
k8s cluster alongside CourtListener itself.

### Architecture

```
                                    ┌─── k8s cluster ────────────────────────┐
                                    │                                        │
┌─────────────┐     HTTPS     ┌────┴────────┐                               │
│  MCP Client │ ─────────────►│   Ingress   │                               │
│  (Claude,   │  Streamable   │  Controller │                               │
│   Cursor)   │  HTTP + Auth  └──┬──────┬───┘                               │
└─────────────┘                  │      │                                    │
                                 │      │                                    │
                    ┌────────────▼──┐ ┌─▼────────────────┐    ┌────────────┐│
                    │  MCP Server   │ │ Staging OAuth App │    │   Redis    ││
                    │  (Deployment) │ │ (Deployment)      │    │ (optional) ││
                    │  Port 8000    │ │ Stage 2 only      │    │            ││
                    └───────┬───────┘ └──────────────────-┘    └────────────┘│
                            │                                                │
                            │ HTTPS                                          │
                    ┌───────▼───────┐                                        │
                    │ CourtListener │                                        │
                    │ API           │                                        │
                    └───────────────┘                                        │
                                    └────────────────────────────────────────┘
```

### Why k8s (not Fly.io/Railway)

- **Same infrastructure** as CL — no new vendor, billing, or deploy tooling
- **Ingress already solved** — adding `mcp.courtlistener.com` is one rule
- **Staging OAuth app** is just another service in the same namespace
- **Readiness/liveness probes** work with the `/health` endpoint
- **HPA** for autoscaling if needed later

### K8s Resources Needed

**MCP Server:**
- `Deployment` — runs the Dockerfile with `MCP_TRANSPORT=streamable-http`
- `Service` (ClusterIP) — exposes port 8000
- `Ingress` — TLS termination, routes `mcp.courtlistener.com/mcp`
- `ConfigMap` — `MCP_TRANSPORT`, `MCP_PORT`, etc.

**Staging OAuth App (Stage 2):**
- `Deployment` — small Django app
- `Service` (ClusterIP) — internal only, not exposed to internet
- `ConfigMap` / `Secret` — Django settings, OAuth keys

**Optional (Stage 3 / production hardening):**
- `Redis` — shared session store for horizontal scaling
- `NetworkPolicy` — restrict traffic between pods
- `PodDisruptionBudget` — maintain availability during rollouts

### Session State Strategy

| Stage | Approach | Tradeoff |
|-------|----------|----------|
| 1 | In-memory dict, single replica | Simple, loses state on restart |
| 1+ | Session affinity in ingress | Allows multiple replicas, no shared state |
| 3 | Redis-backed sessions | Full horizontal scaling, state survives restarts |

---

## Security Considerations

1. **TLS everywhere** — all traffic between MCP client → server → CL API
   must be HTTPS
2. **Token storage** — if storing CL tokens server-side (OAuth flow),
   encrypt at rest
3. **Rate limiting** — the remote server should enforce its own rate limits
   to prevent abuse, in addition to CL's 5,000 req/hr limit
4. **Audit logging** — log tool invocations per user for abuse detection
5. **Token scoping** — if CL adds scoped tokens in the future, request
   minimal permissions
6. **No token logging** — never log API tokens in request logs
7. **PKCE required** — MCP spec mandates PKCE (S256) for all OAuth clients

---

## Implementation Checklist

### Stage 1: Streamable HTTP + Header Auth ✅
- [x] Add Streamable HTTP transport option to `server.py`
- [x] Refactor `MCPTool.get_client()` to accept token from request context
- [x] Add auth middleware for header-based token extraction
- [x] Add Dockerfile
- [x] Add health check endpoint
- [x] Add `uvicorn` and `starlette` to `[mcp]` dependencies
- [ ] Add k8s manifests (Deployment, Service, Ingress)
- [ ] Deploy to k8s cluster
- [ ] Update README with remote connection instructions

### Stage 2: Staging OAuth Environment
- [ ] Scaffold staging Django OAuth app with `django-oauth-toolkit`
- [ ] Implement user model + API token binding
- [ ] Add OAuth authorization / token / introspection endpoints
- [ ] Add minimal consent screen
- [ ] Add k8s manifests for the staging app
- [ ] Update MCP server to support `token_verifier` (SDK-native OAuth)
- [ ] Add `AuthSettings` pointing to staging app
- [ ] End-to-end test OAuth flow with Claude Desktop and Cursor
- [ ] Document the scopes/claims spec for CL to implement

### Stage 3: Production OAuth + Hardening
- [ ] Point `issuer_url` to real CL OAuth endpoints
- [ ] Remove staging Django app
- [ ] Add Redis-backed session store for horizontal scaling
- [ ] Add rate limiting and abuse detection
- [ ] Add monitoring and alerting
- [ ] Add usage analytics
- [ ] Load testing

---

## Open Questions

1. **CourtListener OAuth timeline**: When does CL plan to add OAuth? This
   determines how long Stage 2 lives.

2. **Subdomain**: Is `mcp.courtlistener.com` available?

3. **K8s namespace**: Deploy in the same namespace as CL, or a separate one?

4. **Session state urgency**: Is session affinity sufficient for launch, or
   do we need Redis from day one?

5. **Staging OAuth app location**: Separate repo, or a directory in this
   repo (e.g., `staging/oauth-app/`)?

6. **Who operates this?**: Free Law Project infra team? This affects the
   complexity budget for Stage 2/3.
