import os

from fastmcp import FastMCP
from fastmcp.server.auth.auth import (
    AccessToken,
    AuthProvider,
    RemoteAuthProvider,
    TokenVerifier,
)
from fastmcp.server.middleware.caching import ResponseCachingMiddleware
from key_value.aio.stores.redis import RedisStore
from pydantic import AnyHttpUrl
from starlette.responses import JSONResponse

from courtlistener.mcp.middleware import ToolHandlerMiddleware

REDIS_URL = os.getenv("REDIS_URL")

GIT_SHA = os.getenv("GIT_SHA", "unknown")

OAUTH_ISSUER = os.getenv(
    "COURTLISTENER_OAUTH_ISSUER", "https://www.courtlistener.com"
)
MCP_BASE_URL = os.getenv("MCP_BASE_URL", "https://mcp.courtlistener.com")


class PassThroughTokenVerifier(TokenVerifier):
    """Accept any non-empty bearer token without local validation.

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
    """Return an ``AuthProvider`` when OAuth is configured, else ``None``."""
    if os.getenv("MCP_REQUIRE_OAUTH", "true").lower() != "true":
        return None
    return RemoteAuthProvider(
        token_verifier=PassThroughTokenVerifier(base_url=MCP_BASE_URL),
        authorization_servers=[AnyHttpUrl(OAUTH_ISSUER)],
        base_url=MCP_BASE_URL,
    )


def create_mcp_server(**kwargs):
    mcp = FastMCP("courtlistener", **kwargs)

    redis_store = kwargs.get("session_state_store")

    mcp.add_middleware(ToolHandlerMiddleware())

    if redis_store is not None:
        mcp.add_middleware(
            ResponseCachingMiddleware(cache_storage=redis_store)
        )

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
    mcp = create_mcp_server(
        session_state_store=redis_store,
        auth=build_auth(),
    )
    return mcp.http_app(path="/", stateless_http=True)


def main():
    mcp = create_mcp_server()
    mcp.run()


if __name__ == "__main__":
    main()
