import os

from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import JWTVerifier
from key_value.aio.stores.redis import RedisStore
from starlette.responses import JSONResponse

from courtlistener.mcp.middleware import ToolHandlerMiddleware

REDIS_URL = os.getenv("REDIS_URL")
# Baked into production images by the Makefile via a Docker ARG; defaults
# to "unknown" for local / unparametrized builds.
GIT_SHA = os.getenv("GIT_SHA", "unknown")

# Issuer of the bearer tokens we accept. Must match exactly the
# `issuer` field in CourtListener's
# /.well-known/oauth-authorization-server. Override in dev via env.
OAUTH_ISSUER = os.getenv(
    "COURTLISTENER_OAUTH_ISSUER", "https://www.courtlistener.com"
)
MCP_BASE_URL = os.getenv("MCP_BASE_URL", "https://mcp.courtlistener.com")


def build_auth() -> JWTVerifier | None:
    """Return a ``JWTVerifier`` when OAuth is configured, else ``None``.

    Only the HTTP deployment requires OAuth; stdio / local dev can run
    without it. ``MCP_REQUIRE_OAUTH`` is the opt-in switch.
    """
    if not os.getenv("MCP_REQUIRE_OAUTH"):
        return None
    return JWTVerifier(
        jwks_uri=f"{OAUTH_ISSUER}/o/.well-known/jwks.json",
        issuer=OAUTH_ISSUER,
        # audience left unset — RFC 8707 resource-indicator support on
        # the CL auth-server side is not yet complete. Tighten once
        # django-oauth-toolkit honors `aud == MCP_BASE_URL`.
        audience=None,
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
    # of create_mcp_server() continue to run without a JWT verifier.
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
