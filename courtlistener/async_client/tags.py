from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from courtlistener.async_client.resource import AsyncResource
from courtlistener.models.endpoints.docket_tags import DocketTagsEndpoint
from courtlistener.models.endpoints.tags import TagsEndpoint
from courtlistener.models.tags import DocketTagCreate, TagCreate, TagUpdate

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
        """Create a new tag. ``name`` is a slug, unique among the user's
        tags."""
        validated = TagCreate(
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
        validated = TagUpdate(**data)
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


class AsyncDocketTags(AsyncResource):
    """Helper for adding dockets to tags and removing them."""

    def __init__(self, client: AsyncCourtListener) -> None:
        super().__init__(client, DocketTagsEndpoint)

    async def create(self, tag: int, docket: int) -> dict[str, Any]:
        """Add a docket to one of the user's tags."""
        validated = DocketTagCreate(tag=tag, docket=docket)
        return cast(
            dict[str, Any],
            await self._client._request(
                "POST", self._endpoint, json=validated.model_dump()
            ),
        )

    async def delete(self, id: int) -> None:
        """Remove a docket from a tag by the docket tag's ID."""
        await self._client._request("DELETE", f"{self._endpoint}{id}/")

    async def add(self, tag: int, docket: int) -> dict[str, Any]:
        """Add a docket to a tag unless it is already there."""
        async for docket_tag in self.list(tag=tag, docket=docket):
            return {**docket_tag, "already_tagged": True}

        return await self.create(tag, docket)

    async def remove(self, tag: int, docket: int) -> None:
        """Remove a docket from a tag by tag and docket ID."""
        async for docket_tag in self.list(tag=tag, docket=docket):
            await self.delete(docket_tag["id"])
            return
        raise ValueError(f"Docket {docket} is not in tag {tag}")
