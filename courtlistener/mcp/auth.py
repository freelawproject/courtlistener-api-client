import base64
import binascii
import logging
import time
from typing import Any, NoReturn
from urllib.parse import unquote

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client
from fastmcp.server.auth.auth import (
    AccessToken,
    PrivateKeyJWTClientAuthenticator,
    TokenHandler,
    TokenVerifier,
)
from fastmcp.server.auth.oauth_proxy import OAuthProxy
from fastmcp.server.auth.oauth_proxy.models import HTTP_TIMEOUT_SECONDS
from mcp.server.auth.middleware.auth_context import AuthContextMiddleware
from mcp.server.auth.middleware.bearer_auth import (
    AuthenticatedUser,
    BearerAuthBackend,
)
from mcp.server.auth.provider import TokenVerifier as TokenVerifierProtocol
from mcp.server.auth.routes import cors_middleware
from starlette.authentication import AuthCredentials
from starlette.datastructures import FormData
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import HTTPConnection, Request
from starlette.responses import Response
from starlette.routing import Route

from courtlistener.mcp.auth_types import ResolvedToken, TokenInfo, TokenKind
from courtlistener.mcp.session import get_session, hmac_hex
from courtlistener.mcp.settings import (
    OAUTH_CLIENT_ID,
    OAUTH_CLIENT_SECRET,
    OAUTH_INTROSPECTION_URL,
    TOKEN_CACHE_TTL_SECONDS,
    VERIFICATION_TIMEOUT_SECONDS,
)
from courtlistener.settings import get_api_base_url

logger = logging.getLogger(__name__)


def _assert_unhandled_token_kind(value: NoReturn) -> NoReturn:
    """Exhaustiveness guard for mypy."""
    raise AssertionError(f"unhandled token kind: {value!r}")


async def introspect_token(token: str) -> TokenInfo | None:
    """Return token info if *token* is an active CourtListener access token."""
    if not (OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET):
        logger.error(
            "COURTLISTENER_OAUTH_CLIENT_ID and COURTLISTENER_OAUTH_CLIENT_SECRET "
            "are required to introspect tokens"
        )
        return None
    try:
        async with httpx.AsyncClient(
            timeout=VERIFICATION_TIMEOUT_SECONDS
        ) as http:
            resp = await http.post(
                OAUTH_INTROSPECTION_URL,
                data={"token": token, "token_type_hint": "access_token"},
                auth=(OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET),
            )
    except httpx.HTTPError as exc:
        logger.warning("introspection call failed: %s", exc)
        return None
    if resp.status_code != 200:
        logger.warning("introspection returned HTTP %s", resp.status_code)
        return None
    data = resp.json()
    if not data.get("active"):
        return None
    sub = data.get("sub")
    if not sub:
        logger.warning("introspection response missing `sub`")
        return None
    exp = data.get("exp")
    return TokenInfo(
        user_hash=hmac_hex(str(sub)),
        scopes=str(data.get("scope") or "").split(),
        expires_at=int(exp) if exp else None,
    )


async def verify_api_token(token: str) -> TokenInfo | None:
    """Return token info if *token* is a valid CL API token."""
    try:
        async with httpx.AsyncClient(
            timeout=VERIFICATION_TIMEOUT_SECONDS
        ) as http:
            resp = await http.get(
                f"{get_api_base_url()}/",
                headers={"Authorization": f"Token {token}"},
            )
    except httpx.HTTPError as exc:
        logger.warning("api-token validation call failed: %s", exc)
        return None
    if 200 <= resp.status_code < 300:
        return TokenInfo(user_hash=hmac_hex(token))
    return None


def cache_ttl(info: TokenInfo) -> int:
    """How long to cache *info*: the configured TTL, cut at the token's expiry."""
    expires_at = info.get("expires_at")
    if expires_at is None:
        return TOKEN_CACHE_TTL_SECONDS
    return max(1, min(TOKEN_CACHE_TTL_SECONDS, expires_at - int(time.time())))


async def resolve_token(
    token: str, *, kind: TokenKind
) -> ResolvedToken | None:
    """Verify *token* as a credential of *kind*, or return ``None``."""
    session = get_session()
    cached = await session.get_token_info(token, kind)
    if cached:
        return ResolvedToken(**cached, kind=kind, cached=True)

    if kind == TokenKind.OAUTH:
        info = await introspect_token(token)
    elif kind == TokenKind.API:
        info = await verify_api_token(token)
    else:
        _assert_unhandled_token_kind(kind)
    if info is None:
        return None

    logger.info("verified %s credential", kind)
    await session.store_token_info(token, kind, info, cache_ttl(info))
    return ResolvedToken(**info, kind=kind, cached=False)


class CourtListenerTokenVerifier(TokenVerifier):
    """Verify CourtListener credentials: OAuth tokens by introspection, API tokens by a CL call."""

    def __init__(self, *, base_url: str) -> None:
        super().__init__(base_url=base_url, required_scopes=["api"])

    async def verify_token(
        self, token: str, kind: TokenKind = TokenKind.OAUTH
    ) -> AccessToken | None:
        """Verify *token* as a credential of *kind*."""
        if not token:
            return None
        info = await resolve_token(token, kind=kind)
        if info is None:
            return None
        return AccessToken(
            token=token,
            client_id="courtlistener-mcp",
            # API tokens lack OAuth scopes; echo the required set.
            scopes=info.get("scopes") or list(self.required_scopes),
            expires_at=info.get("expires_at"),
            claims={
                "user_hash": info["user_hash"],
                "token_kind": info["kind"],
                "cached": info["cached"],
            },
        )


class CourtListenerAuthBackend(BearerAuthBackend):
    """Authenticate CL ``Token`` credentials as well as ``Bearer`` ones."""

    def __init__(
        self,
        bearer_verifier: TokenVerifierProtocol,
        api_verifier: CourtListenerTokenVerifier,
    ) -> None:
        super().__init__(bearer_verifier)
        self.api_verifier = api_verifier

    async def authenticate(self, conn: HTTPConnection):
        auth_header = next(
            (
                conn.headers.get(key)
                for key in conn.headers
                if key.lower() == "authorization"
            ),
            None,
        )
        if not auth_header:
            return None

        scheme, _, credential = auth_header.partition(" ")
        kind = TokenKind.from_scheme(scheme)
        # Bearer stays byte-exact via the parent; only Token strips.
        credential = credential.strip()
        if kind is None or not credential:
            return None
        if kind is TokenKind.OAUTH:
            return await super().authenticate(conn)

        auth_info = await self.api_verifier.verify_token(credential, kind)
        if not auth_info:
            return None
        if auth_info.expires_at and auth_info.expires_at < int(time.time()):
            return None
        return AuthCredentials(auth_info.scopes), AuthenticatedUser(auth_info)


class ResourceIndicatorClient(AsyncOAuth2Client):
    """authlib client that sends RFC 8707 ``resource`` values with token requests."""

    def __init__(
        self, *args: Any, resources: list[str], **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self.resources = list(resources)

    async def post(
        self, url: Any, *, data: Any = None, **kwargs: Any
    ) -> httpx.Response:
        if isinstance(data, dict) and "grant_type" in data:
            data = {**data, "resource": self.resources}
        return await super().post(url, data=data, **kwargs)


class BasicAuthTokenHandler(TokenHandler):
    """Token handler accepting ``client_secret_basic`` requests that omit ``client_id`` from the body."""

    async def handle(self, request: Request) -> Response:
        form = await request.form()
        header = request.headers.get("Authorization", "")
        if not form.get("client_id") and header.startswith("Basic "):
            try:
                decoded = base64.b64decode(header[6:]).decode("utf-8")
            except (ValueError, UnicodeDecodeError, binascii.Error):
                decoded = ""
            if client_id := unquote(decoded.partition(":")[0]):
                request._form = FormData(
                    [*form.multi_items(), ("client_id", client_id)]
                )
        return await super().handle(request)


class CourtListenerOAuthProxy(OAuthProxy):
    """Authorization server for MCP clients that brokers CourtListener logins."""

    def __init__(
        self,
        *,
        token_verifier: CourtListenerTokenVerifier,
        upstream_scopes: list[str],
        upstream_resources: list[str],
        **kwargs: Any,
    ) -> None:
        super().__init__(
            token_verifier=token_verifier,
            valid_scopes=list(upstream_scopes),
            forward_resource=False,
            require_authorization_consent="external",
            **kwargs,
        )
        self.api_verifier = token_verifier
        self.upstream_scopes = list(upstream_scopes)
        self.upstream_resources = list(upstream_resources)

    def _build_upstream_authorize_url(
        self, txn_id: str, transaction: dict[str, Any]
    ) -> str:
        return super()._build_upstream_authorize_url(
            txn_id, {**transaction, "scopes": self.upstream_scopes}
        )

    def _prepare_scopes_for_token_exchange(
        self, scopes: list[str]
    ) -> list[str]:
        return []

    def _create_upstream_oauth_client(self) -> AsyncOAuth2Client:
        return ResourceIndicatorClient(
            resources=self.upstream_resources,
            client_id=self._upstream_client_id,
            client_secret=(
                self._upstream_client_secret.get_secret_value()
                if self._upstream_client_secret is not None
                else None
            ),
            token_endpoint_auth_method=self._token_endpoint_auth_method,
            timeout=HTTP_TIMEOUT_SECONDS,
        )

    def get_routes(self, mcp_path: str | None = None) -> list[Route]:
        routes = super().get_routes(mcp_path)
        for i, route in enumerate(routes):
            if route.path == "/token" and self._cimd_manager is not None:
                handler = BasicAuthTokenHandler(
                    provider=self,
                    client_authenticator=PrivateKeyJWTClientAuthenticator(
                        provider=self,
                        cimd_manager=self._cimd_manager,
                        token_endpoint_url=f"{str(self.base_url).rstrip('/')}/token",
                    ),
                )
                routes[i] = Route(
                    "/token",
                    endpoint=cors_middleware(
                        handler.handle, ["POST", "OPTIONS"]
                    ),
                    methods=["POST", "OPTIONS"],
                )
            elif route.path == "/.well-known/oauth-authorization-server":
                routes.append(
                    Route(
                        "/.well-known/openid-configuration",
                        endpoint=route.endpoint,
                        methods=list(route.methods or []),
                    )
                )
        return routes

    def get_middleware(self) -> list:
        return [
            Middleware(
                AuthenticationMiddleware,
                backend=CourtListenerAuthBackend(self, self.api_verifier),
            ),
            Middleware(AuthContextMiddleware),
        ]
