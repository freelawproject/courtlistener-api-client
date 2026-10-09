import logging
import time
from typing import NoReturn

import httpx
from fastmcp.server.auth.auth import (
    AccessToken,
    RemoteAuthProvider,
    TokenVerifier,
)
from mcp.server.auth.middleware.auth_context import AuthContextMiddleware
from mcp.server.auth.middleware.bearer_auth import (
    AuthenticatedUser,
    BearerAuthBackend,
)
from starlette.authentication import AuthCredentials
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import HTTPConnection

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


async def verify_oauth_token(token: str) -> TokenInfo | None:
    """Return token info if CourtListener reports *token* as an active
    access token issued to a user."""
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
        logger.warning("introspection response has no `sub`")
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
        info = await verify_oauth_token(token)
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
    """Verify CourtListener credentials: OAuth tokens by introspection,
    API tokens by a call to the API."""

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

    token_verifier: CourtListenerTokenVerifier

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

        auth_info = await self.token_verifier.verify_token(credential, kind)
        if not auth_info:
            return None
        if auth_info.expires_at and auth_info.expires_at < int(time.time()):
            return None
        return AuthCredentials(auth_info.scopes), AuthenticatedUser(auth_info)


class CourtListenerAuthProvider(RemoteAuthProvider):
    """``RemoteAuthProvider`` whose HTTP layer accepts both schemes."""

    token_verifier: CourtListenerTokenVerifier

    def get_middleware(self) -> list:
        # AuthProvider.get_middleware (fastmcp==3.4.0), backend swapped.
        return [
            Middleware(
                AuthenticationMiddleware,
                backend=CourtListenerAuthBackend(self.token_verifier),
            ),
            Middleware(AuthContextMiddleware),
        ]
