"""Shared HTTP helper for the Free Law wiki tools.

The wiki tools don't go through the CourtListener API client at all —
they call the wiki's read-only JSON API (``wiki/api/`` in
freelawproject/wiki), forwarding the same OAuth bearer token FastMCP
already verified for this request. On the wiki side the token is
introspected against CourtListener (requiring the ``wiki:read`` scope),
the account email is mapped through the wiki's sign-in allowlist, and
every response is scoped by the wiki's ordinary page permissions.
Without a token the wiki serves public pages only, so the tools also
work in unauthenticated and stdio setups.
"""

from typing import Any

import httpx
from fastmcp.server.dependencies import get_access_token

from courtlistener.mcp.settings import (
    WIKI_API_BASE_URL,
    WIKI_API_TIMEOUT_SECONDS,
)


async def wiki_get(path: str, params: dict[str, Any] | None = None) -> dict:
    """GET a wiki API path, forwarding the request's bearer token.

    Raises ``httpx.HTTPStatusError`` on non-2xx responses; tools turn
    the 404 case into a friendly message.
    """
    headers = {}
    access_token = get_access_token()
    if access_token is not None:
        headers["Authorization"] = f"Bearer {access_token.token}"

    async with httpx.AsyncClient(timeout=WIKI_API_TIMEOUT_SECONDS) as http:
        response = await http.get(
            f"{WIKI_API_BASE_URL.rstrip('/')}{path}",
            params=params,
            headers=headers,
        )
    response.raise_for_status()
    return response.json()
