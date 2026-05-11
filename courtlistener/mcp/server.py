import base64
import os

from fastmcp import FastMCP
from fastmcp.server.auth.auth import (
    AuthProvider,
    RemoteAuthProvider,
)
from fastmcp.server.middleware.caching import ResponseCachingMiddleware
from key_value.aio.stores.redis import RedisStore
from mcp.types import Icon
from pydantic import AnyHttpUrl
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
)

from courtlistener.mcp.auth import UserInfoTokenVerifier
from courtlistener.mcp.middleware import ToolHandlerMiddleware
from courtlistener.mcp.prompts import GLOBAL_INSTRUCTIONS
from courtlistener.mcp.tools.utils import (
    BASE_DIR,
    GIT_SHA,
    MCP_BASE_URL,
    OAUTH_ISSUER,
    REDIS_URL,
)

ICON_CACHE_HEADERS = {"Cache-Control": "public, max-age=86400"}

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CourtListener MCP Server</title>
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta name="google-site-verification" content="C8dEEUUkQm1uhzt8FLvr1mAKcuEOkMiTi5a0nFgs5Qw" />
<meta name="description" content="MCP (Model Context Protocol) server for the CourtListener legal research API.">
<style>
body { font-family: system-ui, sans-serif; max-width: 40rem; margin: 4rem auto; padding: 0 1rem; line-height: 1.5; color: #222; }
a { color: #b53c2c; }
code { background: #f4f4f4; padding: 0.1em 0.3em; border-radius: 3px; }
</style>
</head>
<body>
<h1>CourtListener MCP Server</h1>
<p>This is the HTTP endpoint for the CourtListener Model Context Protocol server,
which exposes the <a href="https://courtlistener.com">CourtListener</a> legal
research API to MCP-compatible clients.</p>
<p>See the <a href="https://wiki.free.law/c/courtlistener/help/api/mcp">MCP documentation</a> on the Free Law Wiki for setup instructions.</p>
</body>
</html>
"""


def create_mcp_server(**kwargs):
    assets_dir = BASE_DIR / "mcp" / "assets"
    favicon_svg_path = assets_dir / "favicon.svg"
    favicon_ico_path = assets_dir / "favicon.ico"
    apple_touch_path = assets_dir / "apple-touch-icon.png"

    favicon_b64 = base64.b64encode(favicon_svg_path.read_bytes()).decode(
        "utf-8"
    )
    apple_touch_b64 = base64.b64encode(apple_touch_path.read_bytes()).decode(
        "utf-8"
    )

    mcp = FastMCP(
        name="CourtListener",
        instructions=GLOBAL_INSTRUCTIONS,
        website_url="https://courtlistener.com",
        icons=[
            Icon(
                src=f"data:image/svg+xml;base64,{favicon_b64}",
                mimeType="image/svg+xml",
                sizes=["16x16", "32x32"],
            ),
            Icon(
                src=f"data:image/png;base64,{apple_touch_b64}",
                mimeType="image/png",
                sizes=["180x180"],
            ),
        ],
        **kwargs,
    )

    redis_store = kwargs.get("session_state_store")

    mcp.add_middleware(ToolHandlerMiddleware())

    if redis_store is not None:
        mcp.add_middleware(
            ResponseCachingMiddleware(cache_storage=redis_store)
        )

    # Static asset routes
    @mcp.custom_route("/favicon.svg", methods=["GET"])
    async def favicon_svg(request):
        return FileResponse(
            favicon_svg_path,
            media_type="image/svg+xml",
            headers=ICON_CACHE_HEADERS,
        )

    @mcp.custom_route("/favicon.ico", methods=["GET"])
    async def favicon_ico(request):
        return FileResponse(
            favicon_ico_path,
            media_type="image/x-icon",
            headers=ICON_CACHE_HEADERS,
        )

    @mcp.custom_route("/apple-touch-icon.png", methods=["GET"])
    async def apple_touch_icon(request):
        return FileResponse(
            apple_touch_path,
            media_type="image/png",
            headers=ICON_CACHE_HEADERS,
        )

    # Home page route
    @mcp.custom_route("/", methods=["GET"])
    async def index(request):
        return HTMLResponse(INDEX_HTML)

    # Health check route
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


def build_auth() -> AuthProvider | None:
    """Return an ``AuthProvider`` when OAuth is configured, else ``None``."""
    if os.getenv("MCP_REQUIRE_OAUTH", "true").lower() != "true":
        return None
    return RemoteAuthProvider(
        token_verifier=UserInfoTokenVerifier(base_url=MCP_BASE_URL),
        authorization_servers=[AnyHttpUrl(OAUTH_ISSUER)],
        base_url=MCP_BASE_URL,
    )


def create_http_app():
    if REDIS_URL is None:
        raise ValueError("REDIS_URL is required for HTTP mode")
    redis_store = RedisStore(url=REDIS_URL)
    mcp = create_mcp_server(
        session_state_store=redis_store,
        auth=build_auth(),
    )
    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=[
                "mcp-protocol-version",
                "mcp-session-id",
                "Authorization",
                "Content-Type",
            ],
            expose_headers=["mcp-session-id"],
        )
    ]
    return mcp.http_app(path="/", stateless_http=True, middleware=middleware)


def main():
    mcp = create_mcp_server()
    mcp.run()


if __name__ == "__main__":
    main()
