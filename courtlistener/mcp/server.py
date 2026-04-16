import os

from fastmcp import FastMCP
from fastmcp.server.auth.auth import (
    AccessToken,
    AuthProvider,
    RemoteAuthProvider,
    TokenVerifier,
)
from key_value.aio.stores.redis import RedisStore
from starlette.responses import JSONResponse

from courtlistener.mcp.middleware import ToolHandlerMiddleware

REDIS_URL = os.getenv("REDIS_URL")
# Baked into production images by the Makefile via a Docker ARG; defaults
# to "unknown" for local / unparametrized builds.
GIT_SHA = os.getenv("GIT_SHA", "unknown")

# OAuth authorization server that issues the bearer tokens we accept.
# Advertised to clients via the RFC 9728
# /.well-known/oauth-protected-resource metadata so they know which
# server to register with and obtain tokens from. Override in dev via env.
OAUTH_ISSUER = os.getenv(
    "COURTLISTENER_OAUTH_ISSUER", "https://www.courtlistener.com"
)
MCP_BASE_URL = os.getenv("MCP_BASE_URL", "https://mcp.courtlistener.com")


class PassThroughTokenVerifier(TokenVerifier):
    """Accept any non-empty bearer token without local validation.

    The MCP server is a thin proxy in front of the CourtListener API:
    every authenticated request ultimately forwards the same bearer
    token to CL, where DRF's ``OAuth2Authentication`` performs the real
    check (signature, expiry, revocation, user lookup). Re-validating
    here would duplicate that work and force us to either fetch JWKS,
    run token introspection, or persist JWT-sized access tokens in
    DOT's stock ``CharField(255)``. Deferring to CL keeps it as the
    single source of truth for token validity and leaves the MCP
    stateless.

    FastMCP still needs an ``AuthProvider`` to wire the OAuth discovery
    routes (``/.well-known/oauth-protected-resource``) and to reject
    anonymous requests with a ``WWW-Authenticate`` header that points
    clients at the authorization server. That's what this verifier +
    the ``RemoteAuthProvider`` wrapper below provide — nothing more.

    Known limitation: a bearer token that CL later rejects (expired or
    revoked mid-session) surfaces as a tool-level error rather than an
    HTTP 401 from the MCP, so clients won't automatically re-run the
    OAuth flow. Proactive refresh-token handling in MCP clients covers
    the common case; revisit with explicit 401 translation if the edge
    case starts biting in practice.
    """

    async def verify_token(self, token: str) -> AccessToken | None:
        if not token:
            return None
        # ``client_id`` is required by AccessToken but unused on our
        # path; CL resolves the real client/user from the token itself.
        return AccessToken(
            token=token,
            client_id="courtlistener-mcp-passthrough",
            scopes=[],
        )


def build_auth() -> AuthProvider | None:
    """Return an ``AuthProvider`` when OAuth is configured, else ``None``.

    Wraps the pass-through token verifier in a ``RemoteAuthProvider``
    so the MCP publishes discovery metadata pointing clients at CL's
    authorization server. Actual token validation happens downstream
    when the tool code forwards the bearer to the CourtListener API.

    Only the HTTP deployment requires OAuth; stdio / local dev can run
    without it. Set ``MCP_REQUIRE_OAUTH=true`` to opt in (the literal
    string ``"true"`` — any other value leaves OAuth off).
    """
    if os.getenv("MCP_REQUIRE_OAUTH", "").lower() != "true":
        return None
    return RemoteAuthProvider(
        token_verifier=PassThroughTokenVerifier(base_url=MCP_BASE_URL),
        authorization_servers=[OAUTH_ISSUER],
        base_url=MCP_BASE_URL,
    )


def create_mcp_server(**kwargs):
    mcp = FastMCP("courtlistener", **kwargs)

    mcp.add_middleware(ToolHandlerMiddleware())

    @mcp.custom_route("/health", methods=["GET"])
    async def health_check(request):
        services = {"mcp": True}

        redis_store = kwargs.get("session_state_store")
        if redis_store is not None:
            services["redis"] = await redis_store._client.ping()

        return JSONResponse(
            {
                "status": "healthy" if all(services.values()) else "unhealthy",
                "version": GIT_SHA,
                "services": services,
            }
        )

    return mcp


def create_http_app():
    if REDIS_URL is None:
        raise ValueError("REDIS_URL is required for HTTP mode")
    redis_store = RedisStore(url=REDIS_URL)
    # OAuth is only wired up when running in HTTP mode; stdio invocations
    # of create_mcp_server() continue to run without an auth provider.
    mcp = create_mcp_server(
        session_state_store=redis_store,
        auth=build_auth(),
    )
    return mcp.http_app(path="/")


def main():
    mcp = create_mcp_server()
    mcp.run()


if __name__ == "__main__":
    main()
