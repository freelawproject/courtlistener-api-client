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


async def resolve_user_hash_via_userinfo(token: str) -> str | None:
    """Return the stable user_hash for *token*, hitting userinfo on cache miss."""
    session = get_session()
    cached = await session.get_user_hash(token)
    if cached:
        return cached

    try:
        async with httpx.AsyncClient(timeout=USERINFO_TIMEOUT_SECONDS) as http:
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

    uh = hmac_hex(str(sub))
    await session.store_user_hash(token, uh)
    return uh


class UserInfoTokenVerifier(TokenVerifier):
    """Verify OAuth tokens by calling CL's OIDC userinfo endpoint.

    Caches token→user_hash mappings in the session store so a burst of
    tool calls from one session collapses to a single userinfo
    round-trip. The cached ``user_hash`` is a stable HMAC of the OIDC
    ``sub`` claim, so session state survives access-token rotation
    (previously, a refresh silently orphaned the user's namespace).

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
        # ``wiki:read`` is consumed by the Free Law wiki, not by CL:
        # the wiki tools forward the bearer token to the wiki's API,
        # which introspects it against CL and requires that scope
        # before serving anything beyond public pages. Listing it here
        # puts it in the authorize request, so users consent to wiki
        # access explicitly. Deploy ordering: CL must define the scope
        # (cl/settings/third_party/oauth2_provider.py) before this
        # ships, or authorize requests will be rejected as invalid.
        super().__init__(
            base_url=base_url,
            required_scopes=["openid", "api", "wiki:read"],
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
