import base64
import json
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
from mcp.types import Icon
from pydantic import AnyHttpUrl
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    Response,
)

from courtlistener.mcp.middleware import ToolHandlerMiddleware
from courtlistener.mcp.tools.utils import (
    BASE_DIR,
    GIT_SHA,
    MCP_BASE_URL,
    OAUTH_ISSUER,
    REDIS_URL,
    resolve_user_hash_via_userinfo,
)

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CourtListener MCP Server</title>
<link rel="icon" type="image/x-icon" sizes="16x16 32x32" href="/favicon.ico">
<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png">
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png">
<link rel="icon" type="image/png" sizes="48x48" href="/favicon-48x48.png">
<link rel="icon" type="image/png" sizes="96x96" href="/favicon-96x96.png">
<link rel="icon" type="image/png" sizes="192x192" href="/favicon-192x192.png">
<link rel="icon" type="image/png" sizes="256x256" href="/favicon-256x256.png">
<link rel="icon" type="image/png" sizes="512x512" href="/favicon-512x512.png">
<link rel="icon" type="image/svg+xml" sizes="any" href="/favicon.svg">
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
<link rel="manifest" href="/manifest.webmanifest">
<meta name="theme-color" content="#b53c2c">
<meta name="description" content="MCP (Model Context Protocol) server for the CourtListener legal research API.">
<style>
body { font-family: system-ui, sans-serif; max-width: 40rem; margin: 4rem auto; padding: 0 1rem; line-height: 1.5; color: #222; }
a { color: #b53c2c; }
code { background: #f4f4f4; padding: 0.1em 0.3em; border-radius: 3px; }
</style>
</head>
<body>
<h1>CourtListener MCP Server</h1>
<p>This is the HTTP endpoint for the CourtListener
<a href="https://modelcontextprotocol.io/">Model Context Protocol</a> server,
which exposes the <a href="https://courtlistener.com">CourtListener</a> legal
research API to MCP-compatible clients.</p>
<p>See the <a href="https://github.com/freelawproject/courtlistener-api-client">project repository</a> for setup instructions.</p>
</body>
</html>
"""

ICON_CACHE_HEADERS = {"Cache-Control": "public, max-age=86400"}

PNG_ICON_FILES = (
    "favicon-16x16.png",
    "favicon-32x32.png",
    "favicon-48x48.png",
    "favicon-96x96.png",
    "favicon-192x192.png",
    "favicon-256x256.png",
    "favicon-512x512.png",
    "apple-touch-icon.png",
)

WEB_MANIFEST = json.dumps(
    {
        "name": "CourtListener MCP Server",
        "short_name": "CourtListener MCP",
        "description": (
            "MCP server for the CourtListener legal research API."
        ),
        "start_url": "/",
        "display": "browser",
        "background_color": "#ffffff",
        "theme_color": "#b53c2c",
        "icons": [
            {
                "src": "/favicon-192x192.png",
                "sizes": "192x192",
                "type": "image/png",
            },
            {
                "src": "/favicon-512x512.png",
                "sizes": "512x512",
                "type": "image/png",
            },
            {
                "src": "/favicon.svg",
                "sizes": "any",
                "type": "image/svg+xml",
            },
        ],
    }
)


class UserInfoTokenVerifier(TokenVerifier):
    """Verify OAuth tokens by calling CL's OIDC userinfo endpoint.

    Caches token→user_hash mappings in Redis so a burst of tool calls
    from one session collapses to a single userinfo round-trip. The
    cached ``user_hash`` is a stable HMAC of the OIDC ``sub`` claim, so
    session state in Redis survives access-token rotation (previously,
    a refresh silently orphaned the user's namespace).

    Revocation semantics:
    - A freshly-rejected token surfaces here as a 401 from userinfo →
      ``verify_token`` returns ``None`` → the auth middleware sends a
      proper 401 with ``WWW-Authenticate`` so the MCP client re-auths.
    - A token revoked mid-cache keeps working until the TTL expires or
      until ``ToolHandlerMiddleware`` sees a 401 from a downstream CL
      API call, invalidates the cache entry, and forces re-verification
      on the next request.

    Required scopes (advertised in the protected-resource metadata so
    MCP clients include them in the authorize request):
    - ``openid``: needed by DOT's ``/o/userinfo/`` endpoint.
    - ``api``: CL's custom scope for REST API access.
    """

    def __init__(self, *, base_url: str) -> None:
        super().__init__(
            base_url=base_url,
            required_scopes=["openid", "api"],
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        if not token:
            return None
        user_hash = await resolve_user_hash_via_userinfo(token)
        if user_hash is None:
            return None
        # Userinfo doesn't return the token's scopes, but a 200 from it
        # proves the token carries ``openid`` (DOT enforces that). The
        # ``api`` scope is enforced downstream by CL's REST API itself.
        # Echoing the required set back here satisfies the middleware's
        # scope check without a second round-trip to introspection.
        return AccessToken(
            token=token,
            client_id="courtlistener-mcp",
            scopes=list(self.required_scopes),
            claims={"user_hash": user_hash},
        )


def build_auth() -> AuthProvider | None:
    """Return an ``AuthProvider`` when OAuth is configured, else ``None``."""
    if os.getenv("MCP_REQUIRE_OAUTH", "true").lower() != "true":
        return None
    return RemoteAuthProvider(
        token_verifier=UserInfoTokenVerifier(base_url=MCP_BASE_URL),
        authorization_servers=[AnyHttpUrl(OAUTH_ISSUER)],
        base_url=MCP_BASE_URL,
    )


def create_mcp_server(**kwargs):
    assets_dir = BASE_DIR / "mcp" / "assets"
    favicon_svg_path = assets_dir / "favicon.svg"
    favicon_ico_path = assets_dir / "favicon.ico"
    logo_path = assets_dir / "logo.svg"

    favicon_b64 = base64.b64encode(favicon_svg_path.read_bytes()).decode(
        "utf-8"
    )
    logo_b64 = base64.b64encode(logo_path.read_bytes()).decode("utf-8")

    mcp = FastMCP(
        name="CourtListener",
        website_url="https://courtlistener.com",
        icons=[
            Icon(
                src=f"data:image/svg+xml;base64,{favicon_b64}",
                mimeType="image/svg+xml",
                sizes=["16x16", "32x32"],
            ),
            Icon(
                src=f"data:image/svg+xml;base64,{logo_b64}",
                mimeType="image/svg+xml",
                sizes=[
                    "48x48",
                    "64x64",
                    "96x96",
                    "128x128",
                    "256x256",
                    "512x512",
                ],
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

    def _make_png_handler(file_path):
        async def handler(request):
            return FileResponse(
                file_path,
                media_type="image/png",
                headers=ICON_CACHE_HEADERS,
            )

        return handler

    for filename in PNG_ICON_FILES:
        mcp.custom_route(f"/{filename}", methods=["GET"])(
            _make_png_handler(assets_dir / filename)
        )

    @mcp.custom_route("/manifest.webmanifest", methods=["GET"])
    async def manifest(request):
        return Response(
            WEB_MANIFEST,
            media_type="application/manifest+json",
            headers=ICON_CACHE_HEADERS,
        )

    # GET / serves HTML; the MCP transport owns POST/DELETE on the same path.
    @mcp.custom_route("/", methods=["GET"])
    async def index(request):
        return HTMLResponse(INDEX_HTML)

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
