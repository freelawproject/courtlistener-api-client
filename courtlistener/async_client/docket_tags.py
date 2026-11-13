from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from courtlistener.async_client.resource import AsyncResource
from courtlistener.models.docket_tags import DocketTagsCreate
from courtlistener.models.generated.endpoints.docket_tags import (
    DocketTagsEndpoint,
)

if TYPE_CHECKING:
    from courtlistener.async_client.client import AsyncCourtListener


class AsyncDocketTags(AsyncResource):
    """Helper for adding dockets to the user's tags and removing them."""

    def __init__(self, client: AsyncCourtListener) -> None:
        super().__init__(client, DocketTagsEndpoint)

    async def create(self, tag: int, docket: int) -> dict[str, Any]:
        """Add a docket to one of the user's tags."""
        validated = DocketTagsCreate(tag=tag, docket=docket)
        return cast(
            dict[str, Any],
            await self._client._request(
                "POST", self._endpoint, json=validated.model_dump()
            ),
        )

    async def delete(self, id: int) -> None:
        """Remove a docket from a tag, by the docket tag's ID."""
        await self._client._request("DELETE", f"{self._endpoint}{id}/")
