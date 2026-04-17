import os

from fastmcp import FastMCP
from fastmcp.server.middleware.caching import ResponseCachingMiddleware
from key_value.aio.stores.redis import RedisStore
from starlette.responses import JSONResponse

from courtlistener.mcp.middleware import ToolHandlerMiddleware

REDIS_URL = os.getenv("REDIS_URL")
# Baked into production images by the Makefile via a Docker ARG; defaults
# to "unknown" for local / unparametrized builds.
GIT_SHA = os.getenv("GIT_SHA", "unknown")


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
    )
    return mcp.http_app(path="/", stateless_http=True)


def main():
    mcp = create_mcp_server()
    mcp.run()


if __name__ == "__main__":
    main()
