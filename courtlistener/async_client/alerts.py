from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from courtlistener.async_client.resource import AsyncResource
from courtlistener.models.alerts import (
    AlertsCreate,
    AlertsType,
    AlertsUpdate,
    RateType,
)
from courtlistener.models.generated.endpoints.alerts import AlertsEndpoint

if TYPE_CHECKING:
    from courtlistener.async_client.client import AsyncCourtListener


class AsyncAlerts(AsyncResource):
    """Helper for managing search alerts."""

    def __init__(self, client: AsyncCourtListener) -> None:
        super().__init__(client, AlertsEndpoint)

    async def create(
        self,
        name: str,
        query: str | dict[str, Any],
        rate: RateType,
        alert_type: AlertsType | None = None,
    ) -> dict[str, Any]:
        """Create a new search alert."""
        validated = AlertsCreate(
            name=name, query=query, rate=rate, alert_type=alert_type
        )
        body = validated.model_dump(exclude_none=True)
        return cast(
            dict[str, Any],
            await self._client._request("POST", self._endpoint, json=body),
        )

    async def update(self, id: int, **data: Any) -> dict[str, Any]:
        """Update an existing search alert."""
        validated = AlertsUpdate(**data)
        body = validated.model_dump(exclude_none=True)
        return cast(
            dict[str, Any],
            await self._client._request(
                "PATCH", f"{self._endpoint}{id}/", json=body
            ),
        )

    async def delete(self, id: int) -> None:
        """Delete a search alert."""
        await self._client._request("DELETE", f"{self._endpoint}{id}/")
