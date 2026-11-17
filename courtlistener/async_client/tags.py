from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from courtlistener.async_client.resource import AsyncResource
from courtlistener.models.generated.endpoints.tags import TagsEndpoint
from courtlistener.models.tags import TagsCreate, TagsUpdate

if TYPE_CHECKING:
    from courtlistener.async_client.client import AsyncCourtListener


class AsyncTags(AsyncResource):
    """Helper for managing the user's tags.

    Listing returns the user's own tags and every user's published ones.
    """

    def __init__(self, client: AsyncCourtListener) -> None:
        super().__init__(client, TagsEndpoint)

    async def create(
        self,
        name: str,
        title: str | None = None,
        description: str | None = None,
        published: bool | None = None,
    ) -> dict[str, Any]:
        """Create a tag. ``name`` is a slug, unique among the user's tags."""
        validated = TagsCreate(
            name=name,
            title=title,
            description=description,
            published=published,
        )
        body = validated.model_dump(exclude_none=True)
        return cast(
            dict[str, Any],
            await self._client._request("POST", self._endpoint, json=body),
        )

    async def update(self, id: int, **data: Any) -> dict[str, Any]:
        """Update one of the user's tags."""
        validated = TagsUpdate(**data)
        body = validated.model_dump(exclude_none=True)
        return cast(
            dict[str, Any],
            await self._client._request(
                "PATCH", f"{self._endpoint}{id}/", json=body
            ),
        )

    async def delete(self, id: int) -> None:
        """Delete one of the user's tags, removing it from every docket."""
        await self._client._request("DELETE", f"{self._endpoint}{id}/")
