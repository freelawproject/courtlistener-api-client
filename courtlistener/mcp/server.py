import asyncio
import base64
import contextlib

import asyncpg
from fastmcp import FastMCP
from fastmcp.server.auth import AuthProvider
from mcp.types import Icon
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import (
    FileResponse,
    JSONResponse,
    PlainTextResponse,
    Response,
)

from courtlistener.mcp.auth import (
    CourtListenerOAuthProxy,
    CourtListenerTokenVerifier,
)
from courtlistener.mcp.metrics import render_metrics
from courtlistener.mcp.prompts import GLOBAL_INSTRUCTIONS
from courtlistener.mcp.session import RedisSession, get_session
from courtlistener.mcp.settings import (
    BASE_DIR,
    GIT_SHA,
    MCP_BASE_URL,
    MCP_JWT_SIGNING_KEY,
    OAUTH_AUTHORIZATION_URL,
    OAUTH_CLIENT_ID,
    OAUTH_CLIENT_SECRET,
    OAUTH_REFRESH_TOKEN_LIFETIME_SECONDS,
    OAUTH_RESOURCES,
    OAUTH_REVOCATION_URL,
    OAUTH_SCOPES,
    OAUTH_TOKEN_URL,
    OPENAI_APPS_CHALLENGE_TOKEN,
    POSTGRES_CONFIGURED,
    REDIS_URL,
)
from courtlistener.mcp.storage import build_client_storage
from courtlistener.mcp.tools import MCP_TOOLS


def create_mcp_server(auth: AuthProvider | None = None) -> FastMCP:
    assets_dir = BASE_DIR / "mcp" / "assets"
    favicon_svg_path = assets_dir / "favicon.svg"
    favicon_ico_path = assets_dir / "favicon.ico"
    apple_touch_path = assets_dir / "apple-touch-icon.png"
    index_html_path = assets_dir / "index.html"
    icon_cache_headers = {"Cache-Control": "public, max-age=86400"}

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
        tools=list(MCP_TOOLS.values()),
        auth=auth,
        # Tools validate their own arguments; see MCPTool.validate_arguments.
        strict_input_validation=False,
    )

    # Static asset routes
    @mcp.custom_route("/favicon.svg", methods=["GET"])
    async def favicon_svg(request):
        return FileResponse(
            favicon_svg_path,
            media_type="image/svg+xml",
            headers=icon_cache_headers,
        )

    @mcp.custom_route("/favicon.ico", methods=["GET"])
    async def favicon_ico(request):
        return FileResponse(
            favicon_ico_path,
            media_type="image/x-icon",
            headers=icon_cache_headers,
        )

    @mcp.custom_route("/apple-touch-icon.png", methods=["GET"])
    async def apple_touch_icon(request):
        return FileResponse(
            apple_touch_path,
            media_type="image/png",
            headers=icon_cache_headers,
        )

    # Home page route
    @mcp.custom_route("/", methods=["GET"])
    async def index(request):
        return FileResponse(index_html_path, media_type="text/html")

    # OpenAI Apps directory domain-verification challenge
    @mcp.custom_route("/.well-known/openai-apps-challenge", methods=["GET"])
    async def openai_apps_challenge(request):
        return PlainTextResponse(OPENAI_APPS_CHALLENGE_TOKEN)

    # Health check route
    @mcp.custom_route("/health", methods=["GET"])
    async def health_check(request):
        services = {"mcp": True}

        session = get_session()
        if isinstance(session, RedisSession):
            services["redis"] = await session.ping()

        if POSTGRES_CONFIGURED:
            try:
                conn = await asyncpg.connect(timeout=5)
                try:
                    await conn.execute("SELECT 1", timeout=5)
                finally:
                    with contextlib.suppress(Exception):
                        await asyncio.wait_for(conn.close(), 5)
                services["postgres"] = True
            except Exception:
                services["postgres"] = False

        return JSONResponse(
            {
                "status": "healthy" if all(services.values()) else "unhealthy",
                "version": GIT_SHA,
                "services": services,
            }
        )

    @mcp.custom_route("/metrics", methods=["GET"])
    async def metrics(request):
        body, content_type = await render_metrics()
        return Response(body, media_type=content_type)

    return mcp


def create_auth_provider() -> CourtListenerOAuthProxy:
    """The OAuth authorization server fronting CourtListener for MCP clients."""
    if not (OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET):
        raise ValueError(
            "COURTLISTENER_OAUTH_CLIENT_ID and COURTLISTENER_OAUTH_CLIENT_SECRET "
            "are required for HTTP mode"
        )
    return CourtListenerOAuthProxy(
        upstream_authorization_endpoint=OAUTH_AUTHORIZATION_URL,
        upstream_token_endpoint=OAUTH_TOKEN_URL,
        upstream_revocation_endpoint=OAUTH_REVOCATION_URL,
        upstream_client_id=OAUTH_CLIENT_ID,
        upstream_client_secret=OAUTH_CLIENT_SECRET,
        token_verifier=CourtListenerTokenVerifier(base_url=MCP_BASE_URL),
        upstream_scopes=OAUTH_SCOPES,
        upstream_resources=OAUTH_RESOURCES,
        base_url=MCP_BASE_URL,
        client_storage=build_client_storage(),
        jwt_signing_key=MCP_JWT_SIGNING_KEY,
        fallback_refresh_token_expiry_seconds=OAUTH_REFRESH_TOKEN_LIFETIME_SECONDS,
        token_expiry_threshold_seconds=60,
    )


def create_http_app():
    if REDIS_URL is None:
        raise ValueError("REDIS_URL is required for HTTP mode")
    mcp = create_mcp_server(auth=create_auth_provider())
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
