from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from courtlistener.async_client.resource import AsyncResource
from courtlistener.models.docket_alerts import (
    DocketAlertsCreate,
    DocketAlertsType,
    DocketAlertsUpdate,
)
from courtlistener.models.generated.endpoints.docket_alerts import (
    DocketAlertsEndpoint,
)

if TYPE_CHECKING:
    from courtlistener.async_client.client import AsyncCourtListener


class AsyncDocketAlerts(AsyncResource):
    """Helper for managing docket alerts (subscriptions)."""

    def __init__(self, client: AsyncCourtListener) -> None:
        super().__init__(client, DocketAlertsEndpoint)

    async def create(
        self, docket: int, alert_type: DocketAlertsType = 1
    ) -> dict[str, Any]:
        """Create a new docket alert."""
        validated = DocketAlertsCreate(docket=docket, alert_type=alert_type)
        return cast(
            dict[str, Any],
            await self._client._request(
                "POST", self._endpoint, json=validated.model_dump()
            ),
        )

    async def update(self, id: int, **data: Any) -> dict[str, Any]:
        """Update an existing docket alert."""
        validated = DocketAlertsUpdate(**data)
        body = validated.model_dump(exclude_none=True)
        return cast(
            dict[str, Any],
            await self._client._request(
                "PATCH", f"{self._endpoint}{id}/", json=body
            ),
        )

    async def delete(self, id: int) -> None:
        """Delete a docket alert."""
        await self._client._request("DELETE", f"{self._endpoint}{id}/")

    async def subscribe(self, docket: int) -> dict[str, Any]:
        """Subscribe to a docket (convenience for create with type=1)."""
        async for alert in self.list(docket=docket):
            return {**alert, "already_subscribed": True}

        return await self.create(docket, alert_type=1)

    async def unsubscribe(self, docket: int) -> None:
        """Unsubscribe from a docket by docket ID."""
        results = self.list(docket=docket)
        async for alert in results:
            await self.delete(alert["id"])
            return
        raise ValueError(f"No docket alert found for docket {docket}")
