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

## The Auth Problem

This is the central design question. CourtListener's API uses **static API
tokens** (Django REST Framework `Token` auth), not OAuth. Users get a token
from their CourtListener profile and pass it as `Authorization: Token <token>`.

A remote MCP server sits between the user's MCP client (Claude, Cursor, etc.)
and the CourtListener API. It needs the user's token to make API calls on
their behalf. There are several ways to handle this:

### Option A: MCP OAuth Flow → Token Storage (Recommended)

Use the MCP spec's OAuth 2.1 authorization flow to authenticate users, then
store/retrieve their CourtListener API token server-side.

**How it works:**

1. User adds the remote MCP URL to their client
2. Client initiates OAuth 2.1 flow (as required by the MCP spec)
3. User is redirected to a CourtListener-hosted login/consent page
4. On consent, the server stores a mapping: `user_id → CL API token`
5. Server issues its own OAuth access token to the MCP client
6. On each tool call, the server looks up the user's CL token and proxies
   the request

**Pros:**
- Best UX — users just click "authorize" in their MCP client
- Follows the MCP authorization spec (November 2025 revision)
- Tokens never leave the server
- Works with Claude Desktop, Cursor, and all spec-compliant clients
- Can revoke access per-user

**Cons:**
- Requires building an authorization server (or using Auth0/Stytch/etc.)
- CourtListener would need a consent/authorization page
- More infrastructure to maintain

**Implementation path:**
- Use Cloudflare Workers with `workers-oauth-provider`, OR
- Build a lightweight auth layer with Auth0/Stytch as the identity provider
  and CourtListener as the consent/token-binding step

### Option B: Header-Based Token Passthrough

The MCP client passes the user's CourtListener API token directly in an HTTP
header, and the server uses it for upstream requests without storing it.

**How it works:**

1. User configures their MCP client with the remote URL AND their API token
   as a custom header (e.g., `Authorization: Token <token>`)
2. Server reads the token from the incoming request and uses it for CL API
   calls

**Pros:**
- Simplest to implement — no auth server needed
- Stateless — server stores nothing
- Token never persisted server-side

**Cons:**
- Not all MCP clients support custom headers (Claude Desktop does via
  config; others may not)
- Not spec-compliant (MCP spec expects OAuth 2.1)
- Less secure in transit if TLS is misconfigured
- Users must manually manage tokens in their config

**Implementation path:**
- Add Streamable HTTP transport to the existing server
- Deploy behind a reverse proxy with TLS
- Document per-client header configuration

### Option C: Hybrid (Recommended for Phased Rollout)

Start with **Option B** (header passthrough) for immediate deployment, then
layer on **Option A** (OAuth) as the spec-compliant path.

**Phase 1 — Ship fast:**
- Deploy with Streamable HTTP transport
- Accept `Authorization: Token <token>` header directly
- Works immediately with clients that support custom headers

**Phase 2 — Ship right:**
- Add OAuth 2.1 flow using an auth provider
- CourtListener login page as the consent screen
- Bind CL API tokens to OAuth sessions
- Keep header passthrough as a fallback

---

## Transport: Streamable HTTP

The current server uses stdio. Remote deployment requires switching to
**Streamable HTTP** (the MCP spec's standard remote transport since March
2025, replacing deprecated SSE).

### Changes Required to `server.py`

The `mcp` Python SDK supports this natively. The key change:

```python
# Before (stdio — local only)
from mcp.server.stdio import stdio_server

async def run():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, ...)

# After (Streamable HTTP — remote)
from mcp.server import Server

app = Server("courtlistener")
# ... register tools as before ...

# Expose as ASGI app via streamable_http_app()
# Mount with: uvicorn or deploy to Cloudflare/Fly/Railway
```

The server should support **both transports** — stdio for local use (existing
behavior) and Streamable HTTP for remote use — selectable via CLI flag or
environment variable.

### Session Management

The current server uses a module-level `session: dict = {}` for pagination
state and citation job tracking. For remote deployment:

- **Stateless mode** (`stateless_http=True`): Each request is independent.
  Pagination state would need to be serialized into the response and passed
  back by the client. Simplest to deploy and scale.
- **Stateful mode**: Server maintains per-session state (current behavior).
  Requires sticky sessions or a shared session store (Redis). Better UX for
  multi-step workflows like citation analysis.

**Recommendation:** Start stateful with a single instance, add Redis-backed
sessions when scaling horizontally.

---

## Deployment Architecture

### Recommended: Fly.io or Railway (Simplest)

```
┌─────────────┐     HTTPS      ┌──────────────────┐     HTTPS     ┌─────────────┐
│  MCP Client │ ──────────────► │  Remote MCP      │ ────────────► │ CourtListener│
│  (Claude,   │  Streamable    │  Server           │  Token auth   │ API          │
│   Cursor)   │  HTTP + Auth   │  (Python/uvicorn) │               │              │
└─────────────┘                └──────────────────┘               └─────────────┘
                                 │
                                 ├── OAuth provider (Phase 2)
                                 └── Session store (Redis, Phase 2)
```

**Why Fly.io/Railway:**
- Native Docker/Python support
- Auto-TLS
- Persistent processes (not just serverless — needed for stateful sessions)
- Simple scaling
- Low cost for a single-instance start

### Alternative: Cloudflare Workers

Best if going OAuth-first (Phase 2 immediately), since `workers-oauth-provider`
handles the entire OAuth flow. However:
- Python support on Workers is newer and has limitations
- The `eyecite` dependency (for local citation extraction) may not work in
  the Workers runtime
- Would require rewriting some tools or proxying citation extraction to a
  separate service

### Alternative: Cloud Run / ECS

Standard container deployment. More operational overhead but familiar to teams
already on GCP/AWS.

---

## Required Code Changes

### 1. Dual-Transport Server Entry Point

Add a new entry point or CLI flag to `server.py`:

```python
def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--transport", choices=["stdio", "streamable-http"],
        default="stdio"
    )
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    if args.transport == "stdio":
        run_stdio()
    else:
        run_http(args.host, args.port)
```

### 2. Per-Request Client Instantiation

Currently `MCPTool.get_client()` reads `COURTLISTENER_API_TOKEN` from the
environment. For remote deployment, the token must come from the request
context (either OAuth session lookup or header passthrough).

The `session` dict already flows through every tool call — extend it to
carry the authenticated user's API token:

```python
class MCPTool:
    def get_client(self, session: dict) -> CourtListener:
        token = session.get("api_token")
        if not token:
            token = os.environ.get("COURTLISTENER_API_TOKEN")
        if not token:
            raise ValueError("No API token available")
        return CourtListener(api_token=token)
```

### 3. Auth Middleware

For Phase 1 (header passthrough), extract the token from the incoming
request's `Authorization` header and inject it into the session dict before
tool execution.

For Phase 2 (OAuth), look up the user's stored CL token from the OAuth
session and inject it the same way.

### 4. Dockerfile

```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY . .
RUN pip install .[mcp]
EXPOSE 8000
CMD ["courtlistener-mcp", "--transport", "streamable-http", "--port", "8000"]
```

### 5. Health Check Endpoint

Add a `/health` endpoint for load balancer probes (standard for any
deployed service).

---

## User Experience (End State)

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "courtlistener": {
      "url": "https://mcp.courtlistener.com/mcp"
    }
  }
}
```

That's it. On first connection, the OAuth flow triggers in the user's browser,
they log into CourtListener, grant consent, and they're connected. No Python,
no pip, no tokens in config files.

### For clients that support headers (Phase 1 fallback)

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

## Implementation Phases

### Phase 1: Streamable HTTP + Header Auth (1-2 weeks)
- [ ] Add Streamable HTTP transport option to `server.py`
- [ ] Refactor `MCPTool.get_client()` to accept token from session context
- [ ] Add auth middleware for header-based token extraction
- [ ] Add Dockerfile
- [ ] Add health check endpoint
- [ ] Deploy to Fly.io or Railway
- [ ] Update README with remote connection instructions

### Phase 2: OAuth 2.1 Authorization (2-4 weeks)
- [ ] Choose auth provider (Auth0, Stytch, or custom)
- [ ] Build CourtListener consent/authorization page
- [ ] Implement token binding (OAuth session → CL API token)
- [ ] Implement Protected Resource Metadata (RFC 9728)
- [ ] Add Dynamic Client Registration support
- [ ] Test with Claude Desktop, Cursor, and other MCP clients
- [ ] Add token encryption at rest

### Phase 3: Production Hardening (Ongoing)
- [ ] Add Redis-backed session store for horizontal scaling
- [ ] Add rate limiting and abuse detection
- [ ] Add monitoring and alerting
- [ ] Add usage analytics
- [ ] Consider multi-region deployment
- [ ] Load testing

---

## Open Questions

1. **CourtListener OAuth support**: Does CourtListener plan to add OAuth to
   its API? If so, the remote MCP server could use standard OAuth token
   exchange instead of storing tokens.

2. **Subdomain**: Is `mcp.courtlistener.com` available and appropriate?

3. **Auth provider preference**: Self-hosted (Keycloak), managed (Auth0,
   Stytch), or Cloudflare Workers OAuth?

4. **Cost/hosting budget**: Fly.io starts ~$5/mo for a small instance. Auth
   providers have free tiers (Auth0: 25k MAU, Stytch: 10k MAU).

5. **Session state strategy**: Should pagination and citation jobs survive
   server restarts? If yes, Redis is needed from Phase 1.

6. **Who operates this?**: Free Law Project infra team? Volunteer-run?
   This affects the complexity budget.
