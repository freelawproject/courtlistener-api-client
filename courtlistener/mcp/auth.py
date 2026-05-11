from fastmcp.server.auth.auth import (
    AccessToken,
    TokenVerifier,
)

from courtlistener.mcp.tools.utils import resolve_user_hash_via_userinfo


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
