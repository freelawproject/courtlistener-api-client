from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from courtlistener.async_client.client import AsyncCourtListener


class AsyncApiUsage:
    """Helper for the API usage endpoint.

    The endpoint has its own throttle scope, so it stays reachable when
    the main API quota is exhausted.
    """

    ENDPOINT = "/api-usage/"

    def __init__(self, client: AsyncCourtListener) -> None:
        self._client = client

    async def get(self) -> dict[str, Any]:
        """Fetch the authenticated user's API usage and rate limits.

        Returns:
            Dict with ``current_usage``, one row per throttle scope and
            rate (``scope``, ``rate``, ``used``, ``limit``, ``remaining``,
            ``window_seconds``, ``reset_at``, ``blocked``);
            ``historical_usage``, daily request counts for the last 14
            days keyed by ISO date plus a ``total``; and ``membership``
            (``level`` and ``is_active``), or ``None`` without one.
        """
        return cast(
            dict[str, Any],
            await self._client._request("GET", self.ENDPOINT),
        )
