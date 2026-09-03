from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from courtlistener.async_client.resource import AsyncResource
from courtlistener.models.endpoints.prayers import PrayersEndpoint
from courtlistener.models.prayers import PrayerCreate

if TYPE_CHECKING:
    from courtlistener.async_client.client import AsyncCourtListener


class AsyncPrayers(AsyncResource):
    """Helper for managing Pray and Pay requests."""

    def __init__(self, client: AsyncCourtListener) -> None:
        super().__init__(client, PrayersEndpoint)

    async def create(self, recap_document: int) -> dict[str, Any]:
        """Create a new prayer for a RECAP document."""
        validated = PrayerCreate(recap_document=recap_document)
        return cast(
            dict[str, Any],
            await self._client._request(
                "POST", self._endpoint, json=validated.model_dump()
            ),
        )

    async def delete(self, id: int) -> None:
        """Delete a prayer that has not yet been granted."""
        await self._client._request("DELETE", f"{self._endpoint}{id}/")
