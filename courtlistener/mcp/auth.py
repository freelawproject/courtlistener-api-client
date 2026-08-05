import logging

import httpx
from fastmcp.server.auth.auth import (
    AccessToken,
    TokenVerifier,
)

from courtlistener.mcp.auth_types import ResolvedToken, TokenInfo, TokenKind
from courtlistener.mcp.session import get_session, hmac_hex
from courtlistener.mcp.settings import (
    OAUTH_USERINFO_URL,
    VERIFICATION_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)


async def verify_oauth_token(token: str) -> TokenInfo | None:
    """Return token info if *token* is a valid OAuth access token."""
    try:
        async with httpx.AsyncClient(
            timeout=VERIFICATION_TIMEOUT_SECONDS
        ) as http:
            resp = await http.get(
                OAUTH_USERINFO_URL,
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError as exc:
        logger.warning("userinfo call failed: %s", exc)
        return None
    if resp.status_code != 200:
        # 401 from userinfo == revoked/expired/invalid. Don't cache.
        return None
    sub = resp.json().get("sub")
    if not sub:
        logger.warning("userinfo response missing `sub` claim")
        return None
    return TokenInfo(user_hash=hmac_hex(str(sub)))


async def resolve_token(
    token: str, *, kind: TokenKind
) -> ResolvedToken | None:
    """Verify *token* as a credential of *kind*, or return ``None``."""
    session = get_session()
    try:
        cached = await session.get_token_info(token, kind)
    except Exception as exc:
        logger.warning("token cache read failed; verifying directly: %s", exc)
        cached = None

    if cached:
        return ResolvedToken(**cached, kind=kind, cached=True)

    if kind == TokenKind.OAUTH:
        info = await verify_oauth_token(token)
    elif kind == TokenKind.API:
        logger.warning("token verification not implemented for %s", kind)
        info = None
    if info is None:
        return None

    logger.info("verified %s credential", kind)
    try:
        await session.store_token_info(token, kind, info)
    except Exception as exc:
        logger.warning("token cache write failed: %s", exc)
    return ResolvedToken(**info, kind=kind, cached=False)


class CourtListenerTokenVerifier(TokenVerifier):
    """Verify CourtListener tokens."""

    def __init__(self, *, base_url: str) -> None:
        super().__init__(
            base_url=base_url,
            required_scopes=["openid", "api"],
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        if not token:
            return None
        # Hardcoded to OAuth until we add API token support.
        info = await resolve_token(token, kind=TokenKind.OAUTH)
        if info is None:
            return None
        return AccessToken(
            token=token,
            client_id="courtlistener-mcp",
            scopes=list(self.required_scopes),
            claims={
                "user_hash": info["user_hash"],
                "token_kind": info["kind"],
                "cached": info["cached"],
            },
        )
