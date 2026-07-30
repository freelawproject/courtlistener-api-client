import logging

import httpx
from fastmcp.server.auth.auth import (
    AccessToken,
    TokenVerifier,
)

from courtlistener.mcp.session import get_session, hmac_hex
from courtlistener.mcp.settings import (
    OAUTH_USERINFO_URL,
    USERINFO_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)


async def resolve_user_hash_via_userinfo(
    token: str,
) -> tuple[str | None, bool]:
    """Verifies token from cache or via CL's `/o/userinfo/` endpoint."""
    session = get_session()
    cached = await session.get_user_hash(token)
    if cached:
        return cached, True

    try:
        async with httpx.AsyncClient(timeout=USERINFO_TIMEOUT_SECONDS) as http:
            resp = await http.get(
                OAUTH_USERINFO_URL,
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError as exc:
        logger.warning("userinfo call failed: %s", exc)
        return None, False

    if resp.status_code != 200:
        # 401 from userinfo == revoked/expired/invalid. Don't cache.
        return None, False

    sub = resp.json().get("sub")
    if not sub:
        logger.warning("userinfo response missing `sub` claim")
        return None, False

    uh = hmac_hex(str(sub))
    await session.store_user_hash(token, uh)
    return uh, False


class UserInfoTokenVerifier(TokenVerifier):
    """Verifies OAuth tokens via CL's `/o/userinfo/` endpoint."""

    def __init__(self, *, base_url: str) -> None:
        super().__init__(
            base_url=base_url,
            required_scopes=["openid", "api"],
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        if not token:
            return None
        user_hash, from_cache = await resolve_user_hash_via_userinfo(token)
        if user_hash is None:
            return None
        return AccessToken(
            token=token,
            client_id="courtlistener-mcp",
            scopes=list(self.required_scopes),
            claims={"user_hash": user_hash, "cached": from_cache},
        )
