import base64
import os
from typing import Any

import asyncpg
from fastmcp import FastMCP
from fastmcp.server.auth import AuthProvider
from mcp.types import Icon
from pydantic import AnyHttpUrl
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import (
    FileResponse,
    JSONResponse,
    PlainTextResponse,
    Response,
)
from starlette.routing import Route

from courtlistener.mcp.auth import (
    CourtListenerAuthProvider,
    CourtListenerTokenVerifier,
)
from courtlistener.mcp.metrics import render_metrics
from courtlistener.mcp.prompts import GLOBAL_INSTRUCTIONS
from courtlistener.mcp.session import RedisSession, get_session
from courtlistener.mcp.settings import (
    BASE_DIR,
    GIT_SHA,
    MCP_BASE_URL,
    OAUTH_ISSUER,
    OPENAI_APPS_CHALLENGE_TOKEN,
    REDIS_URL,
)
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

        return JSONResponse(
            {
                "status": "healthy" if all(services.values()) else "unhealthy",
                "version": GIT_SHA,
                "services": services,
                "storage": await storage_readiness(),
            }
        )

    @mcp.custom_route("/metrics", methods=["GET"])
    async def metrics(request):
        body, content_type = await render_metrics()
        return Response(body, media_type=content_type)

    return mcp


async def storage_readiness() -> dict[str, Any]:
    """Whether the token-store settings are present and usable.

    Informational only: reported by ``/health`` but never part of its status.
    """
    report: dict[str, Any] = {
        name: bool(os.getenv(name))
        for name in (
            "DATABASE_URL",
            "MCP_STORAGE_ENCRYPTION_KEY",
            "MCP_JWT_SIGNING_KEY",
        )
    }
    if key := os.getenv("MCP_STORAGE_ENCRYPTION_KEY"):
        try:
            is_fernet = len(base64.urlsafe_b64decode(key)) == 32
        except ValueError:
            is_fernet = False
        report["encryption_key_format"] = "fernet" if is_fernet else "invalid"
    if url := os.getenv("DATABASE_URL"):
        try:
            conn = await asyncpg.connect(url, timeout=5)
            try:
                await conn.execute("SELECT 1")
            finally:
                await conn.close()
            report["database_ping"] = "ok"
        except Exception as exc:
            report["database_ping"] = f"error: {type(exc).__name__}"
    return report


async def protected_resource_metadata(request):
    # Hand-rolled override of FastMCP/MCP SDK's auto-generated
    # /.well-known/oauth-protected-resource. The SDK types
    # `authorization_servers` as `list[AnyHttpUrl]`, and Pydantic normalizes
    # naked-host URLs by appending `/`, producing
    # `https://www.courtlistener.com/`. DOT's authorization-server metadata
    # advertises `issuer` as `https://www.courtlistener.com` (no slash). RFC
    # 8414 §3 requires byte-identical match, and strict clients (e.g.
    # Anthropic's MCP directory connector) abort the OAuth flow on mismatch.
    return JSONResponse(
        {
            "resource": f"{MCP_BASE_URL.rstrip('/')}/",
            "authorization_servers": [OAUTH_ISSUER.rstrip("/")],
            "scopes_supported": ["openid", "api"],
            "bearer_methods_supported": ["header"],
        },
        headers={"Cache-Control": "public, max-age=3600"},
    )


def create_http_app():
    if REDIS_URL is None:
        raise ValueError("REDIS_URL is required for HTTP mode")
    mcp = create_mcp_server(
        auth=CourtListenerAuthProvider(
            token_verifier=CourtListenerTokenVerifier(base_url=MCP_BASE_URL),
            authorization_servers=[AnyHttpUrl(OAUTH_ISSUER)],
            base_url=MCP_BASE_URL,
        ),
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
    app = mcp.http_app(path="/", stateless_http=True, middleware=middleware)
    # FastMCP appends `@custom_route` handlers *after* the auth provider's
    # routes, so we can't intercept the well-known path via `custom_route`.
    # Prepend directly to the Starlette router (first-match-wins) so our
    # corrected metadata is served instead of the SDK's default.
    app.router.routes.insert(
        0,
        Route(
            "/.well-known/oauth-protected-resource",
            endpoint=protected_resource_metadata,
            methods=["GET", "OPTIONS"],
        ),
    )
    return app


def main():
    mcp = create_mcp_server()
    mcp.run()


if __name__ == "__main__":
    main()
