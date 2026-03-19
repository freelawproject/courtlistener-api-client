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

## Two-Stage Deployment Plan

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

### Stage 2: CourtListener OAuth + Production Hardening

Once CourtListener adds OAuth support (via `django-oauth-toolkit`), the MCP
server switches to standard OAuth 2.1 with PKCE. Users authenticate through
their browser — no tokens in config files.

**What changes on the MCP server:**
- Add SDK-native OAuth support via `token_verifier` parameter
- Add `AuthSettings` with CL as the `issuer_url`
- Keep header passthrough as a fallback for non-OAuth clients
- Tool code stays identical — same `request_api_token` contextvar

**What CL needs to provide:**
- OAuth authorization / token / introspection endpoints (via DOT)
- PKCE support (required by MCP spec)
- Token introspection response that includes the user's CL API token
  (so the MCP server can make upstream API calls on their behalf)
- Scopes: `read` (API read access), `write` (alerts, subscriptions)

**Production hardening (shipped alongside or after OAuth):**
- Redis-backed session store for horizontal scaling
- Rate limiting and abuse detection
- Monitoring and alerting
- Usage analytics

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

The MCP server deploys to the existing Free Law Project k8s cluster alongside
CourtListener itself.

### Architecture

```
                                    ┌─── k8s cluster ────────────────────────┐
                                    │                                        │
┌─────────────┐     HTTPS     ┌────┴────────┐                               │
│  MCP Client │ ─────────────►│   Ingress   │                               │
│  (Claude,   │  Streamable   │  Controller │                               │
│   Cursor)   │  HTTP + Auth  └──────┬──────┘                               │
└─────────────┘                      │                                       │
                                     │                                       │
                        ┌────────────▼──┐    ┌────────────┐                  │
                        │  MCP Server   │    │   Redis    │                  │
                        │  (Deployment) │    │ (Stage 2)  │                  │
                        │  Port 8000    │    │            │                  │
                        └───────┬───────┘    └────────────┘                  │
                                │                                            │
                                │ HTTPS                                      │
                        ┌───────▼───────┐                                    │
                        │ CourtListener │                                    │
                        │ API + OAuth   │                                    │
                        └───────────────┘                                    │
                                    └────────────────────────────────────────┘
```

### Why k8s (not Fly.io/Railway)

- **Same infrastructure** as CL — no new vendor, billing, or deploy tooling
- **Ingress already solved** — adding `mcp.courtlistener.com` is one rule
- **Readiness/liveness probes** work with the `/health` endpoint
- **HPA** for autoscaling if needed later

### K8s Resources Needed

**MCP Server:**
- `Deployment` — runs the Dockerfile with `MCP_TRANSPORT=streamable-http`
- `Service` (ClusterIP) — exposes port 8000
- `Ingress` — TLS termination, routes `mcp.courtlistener.com/mcp`
- `ConfigMap` — `MCP_TRANSPORT`, `MCP_PORT`, etc.

**Stage 2 additions:**
- `Redis` — shared session store for horizontal scaling
- `NetworkPolicy` — restrict traffic between pods
- `PodDisruptionBudget` — maintain availability during rollouts

### Session State Strategy

| Stage | Approach | Tradeoff |
|-------|----------|----------|
| 1 | In-memory dict, single replica | Simple, loses state on restart |
| 1+ | Session affinity in ingress | Allows multiple replicas, no shared state |
| 2 | Redis-backed sessions | Full horizontal scaling, state survives restarts |

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

### Stage 2: CourtListener OAuth + Production Hardening
- [ ] Coordinate with CL on OAuth endpoint implementation (DOT)
- [ ] Define scopes/claims spec for CL's OAuth server
- [ ] Update MCP server to support `token_verifier` (SDK-native OAuth)
- [ ] Add `AuthSettings` pointing to CL's OAuth endpoints
- [ ] End-to-end test OAuth flow with Claude Desktop and Cursor
- [ ] Add Redis-backed session store for horizontal scaling
- [ ] Add rate limiting and abuse detection
- [ ] Add monitoring and alerting
- [ ] Add usage analytics
- [ ] Load testing

---

## Open Questions

1. **CourtListener OAuth timeline**: When does CL plan to add OAuth? This
   determines when Stage 2 can begin.

2. **Subdomain**: Is `mcp.courtlistener.com` available?

3. **K8s namespace**: Deploy in the same namespace as CL, or a separate one?

4. **Session state urgency**: Is session affinity sufficient for launch, or
   do we need Redis from day one?

5. **Who operates this?**: Free Law Project infra team? This affects the
   complexity budget for Stage 2.
