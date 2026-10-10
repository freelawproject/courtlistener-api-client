from __future__ import annotations

import logging
import re
import time
from typing import Any

import httpx
from fastmcp.server.auth.auth import AccessToken, TokenVerifier
from fastmcp.server.auth.oauth_proxy import OAuthProxy
from mcp.server.auth.middleware.auth_context import AuthContextMiddleware
from mcp.server.auth.middleware.bearer_auth import (
    AuthenticatedUser,
    BearerAuthBackend,
)
from mcp.server.auth.provider import TokenVerifier as TokenVerifierProtocol
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl
from starlette.authentication import AuthCredentials
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import HTTPConnection

from courtlistener.mcp.auth_types import TokenInfo, TokenKind
from courtlistener.mcp.metrics import (
    auth_rejections_total,
    oauth_registrations_total,
)
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

# The shape of a client id CourtListener issued when it was the authorization
# server. Clients still holding one are recognised on first use.
LEGACY_CLIENT_ID = re.compile(r"[A-Za-z0-9]{40}")


class CourtListenerOAuthProxy(OAuthProxy):
    """Authorization server for MCP clients that brokers CourtListener
    logins and also accepts CourtListener API tokens."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            token_verifier=OAuthTokenVerifier(),
            forward_resource=False,
            require_authorization_consent="external",
            **kwargs,
        )

    def get_middleware(self) -> list:
        return [
            Middleware(
                AuthenticationMiddleware,
                backend=CourtListenerAuthBackend(self, ApiTokenVerifier()),
            ),
            Middleware(AuthContextMiddleware),
        ]

    async def register_client(
        self, client_info: OAuthClientInformationFull
    ) -> None:
        await super().register_client(client_info)
        oauth_registrations_total.labels(source="dcr").inc()

    async def get_client(
        self, client_id: str
    ) -> OAuthClientInformationFull | None:
        """Registered clients, plus clients registered with CourtListener
        before this server became the authorization server, which are
        registered here the first time they show up."""
        if (client := await super().get_client(client_id)) is not None:
            return client
        if not LEGACY_CLIENT_ID.fullmatch(client_id):
            return None
        await super().register_client(
            OAuthClientInformationFull(
                client_id=client_id,
                redirect_uris=[AnyUrl("http://localhost")],
                grant_types=["authorization_code", "refresh_token"],
                token_endpoint_auth_method="none",
            )
        )
        oauth_registrations_total.labels(source="legacy").inc()
        return await super().get_client(client_id)


class CourtListenerAuthBackend(BearerAuthBackend):
    """``Bearer`` is an MCP-issued token, checked by the proxy; ``Token``
    is a CourtListener API token, checked by *api_verifier*. The scheme
    is binding."""

    def __init__(
        self, proxy: TokenVerifierProtocol, api_verifier: ApiTokenVerifier
    ) -> None:
        super().__init__(proxy)
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
        if kind is TokenKind.OAUTH:
            result = await super().authenticate(conn)
            if result is None:
                auth_rejections_total.labels(scheme=kind.scheme).inc()
            return result
        if kind is not TokenKind.API or not (credential := credential.strip()):
            return None

        auth_info = await self.api_verifier.verify_token(credential)
        if auth_info and (
            not auth_info.expires_at
            or auth_info.expires_at >= int(time.time())
        ):
            return AuthCredentials(auth_info.scopes), AuthenticatedUser(
                auth_info
            )
        auth_rejections_total.labels(scheme=kind.scheme).inc()
        return None


class CachedTokenVerifier(TokenVerifier):
    """Verify one kind of CourtListener credential, caching the result in
    the session store for the token's lifetime or ``TOKEN_CACHE_TTL``."""

    kind: TokenKind

    def __init__(self) -> None:
        super().__init__(required_scopes=["api"])

    async def check(self, token: str) -> TokenInfo | None:
        """Ask CourtListener about *token*; ``None`` when it is not valid."""
        raise NotImplementedError

    async def verify_token(self, token: str) -> AccessToken | None:
        if not token:
            return None
        session = get_session()
        info = await session.get_token_info(token, self.kind)
        cached = info is not None
        if info is None:
            info = await self.check(token)
            if info is None:
                return None
            logger.info("verified %s credential", self.kind)
            await session.store_token_info(
                token, self.kind, info, cache_ttl(info)
            )
        return AccessToken(
            token=token,
            client_id="courtlistener-mcp",
            # API tokens have no scopes of their own; echo the required set.
            scopes=(
                info["scopes"]
                if "scopes" in info
                else list(self.required_scopes)
            ),
            expires_at=info.get("expires_at"),
            claims={
                "user_hash": info["user_hash"],
                "token_kind": self.kind,
                "cached": cached,
            },
        )


class OAuthTokenVerifier(CachedTokenVerifier):
    """A CourtListener OAuth access token, checked by introspection. The
    proxy calls this on the token it holds behind each MCP-issued one."""

    kind = TokenKind.OAUTH

    async def check(self, token: str) -> TokenInfo | None:
        """Introspect *token* at CourtListener with the server's client credentials."""
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
        if resp.status_code in (401, 403):
            logger.error(
                "CourtListener rejected the introspection client credentials"
            )
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


class ApiTokenVerifier(CachedTokenVerifier):
    """A CourtListener API token, checked against the API root."""

    kind = TokenKind.API

    async def check(self, token: str) -> TokenInfo | None:
        """Try *token* against the CourtListener API root."""
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
