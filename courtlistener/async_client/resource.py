from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlparse

from courtlistener.models import Endpoint, Page
from courtlistener.utils import flatten_filters, validate_model_fields

if TYPE_CHECKING:
    from courtlistener.async_client.client import AsyncCourtListener


class AsyncResourceIterator:
    """Iterator for paginated API results."""

    def __init__(
        self,
        resource: AsyncResource,
        filters: dict[str, Any],
    ) -> None:
        self._client = resource._client
        self._endpoint = resource._endpoint
        self._filters = filters
        self._current_page: Page | None = None
        self._count: int | None = None
        self._page_result_index: int = 0

    async def _fetch_page(self, url: str | None = None) -> Page:
        """Fetch a page of results."""
        if url:
            parsed = urlparse(url)
            path = parsed.path
            if parsed.query:
                path = f"{path}?{parsed.query}"
            data = cast(
                dict[str, Any], await self._client._request("GET", path)
            )
        else:
            data = cast(
                dict[str, Any],
                await self._client._request(
                    "GET", self._endpoint, params=self._filters
                ),
            )
        return Page(**data)

    async def get_current_page(self) -> Page:
        """Get the current page."""
        if self._current_page is None:
            self._current_page = await self._fetch_page()
        return self._current_page

    async def has_next(self) -> bool:
        """Whether there is a next page."""
        current_page = await self.get_current_page()
        return current_page.next is not None

    async def has_previous(self) -> bool:
        """Whether there is a previous page."""
        current_page = await self.get_current_page()
        return current_page.previous is not None

    async def next(self) -> None:
        """Get the next page."""
        if not await self.has_next():
            raise ValueError("No next page")
        current_page = await self.get_current_page()
        self._current_page = await self._fetch_page(current_page.next)
        self._page_result_index = 0

    async def previous(self) -> None:
        """Get the previous page."""
        if not await self.has_previous():
            raise ValueError("No previous page")
        current_page = await self.get_current_page()
        self._current_page = await self._fetch_page(current_page.previous)
        self._page_result_index = 0

    async def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        """Iterate over all results across pages, respecting the page result index."""
        while True:
            current_page = await self.get_current_page()
            for item in current_page.results[self._page_result_index :]:
                self._page_result_index += 1
                yield item
            if not await self.has_next():
                break
            await self.next()

    async def get_count(self) -> int:
        """Total count of results across all pages."""
        if self._count is None:
            current_page = await self.get_current_page()
            if current_page.count is None:
                raise ValueError("No count URL")
            elif isinstance(current_page.count, int):
                self._count = current_page.count
            else:
                parsed = urlparse(current_page.count)
                path = parsed.path
                if parsed.query:
                    path = f"{path}?{parsed.query}"
                data = cast(
                    dict[str, Any], await self._client._request("GET", path)
                )
                self._count = int(data.get("count", 0))
        return self._count

    async def get_document_count(self) -> int | None:
        """Total count of nested documents for recap search endpoint."""
        current_page = await self.get_current_page()
        return current_page.document_count

    async def get_results(self) -> list[dict[str, Any]]:
        """Results from the current page."""
        current_page = await self.get_current_page()
        return current_page.results

    async def dump(self) -> dict[str, Any]:
        """Serialize the iterator state to a dict for later restoration."""
        current_page = await self.get_current_page()
        return {
            "current_page": current_page.model_dump(),
            "filters": self._filters,
            "endpoint": self._endpoint,
            "page_result_index": self._page_result_index,
            "count": self._count,
        }

    @classmethod
    def load(
        cls, client: AsyncCourtListener, data: dict[str, Any]
    ) -> AsyncResourceIterator:
        """Restore the iterator from a previously dumped state."""
        iterator = cls.__new__(cls)
        iterator._client = client
        iterator._endpoint = data["endpoint"]
        iterator._filters = data["filters"]
        iterator._current_page = Page(**data["current_page"])
        iterator._page_result_index = data["page_result_index"]
        iterator._count = data["count"]
        return iterator


class AsyncResource:
    """Resource class for API endpoints."""

    def __init__(
        self,
        client: AsyncCourtListener,
        model: type[Endpoint],
    ) -> None:
        self._client = client
        self._model = model
        self._endpoint = model.endpoint

    def validate_filters(self, filters: dict[str, Any]) -> dict[str, Any]:
        filters = self._model(**filters).model_dump(by_alias=True)
        filters = flatten_filters(filters)
        filters = {k: v for k, v in filters.items() if v is not None}
        return filters

    async def get(
        self, id: int | float | str, fields: list[str] | str | None = None
    ) -> dict[str, Any]:
        """Get a resource by its ID."""
        if isinstance(id, float) and id.is_integer():
            id = int(id)
        params = {}
        if fields:
            fields = validate_model_fields(self._model, fields)
            fields_str = ",".join(fields)
            params["fields"] = fields_str
        return cast(
            dict[str, Any],
            await self._client._request(
                "GET", f"{self._endpoint}{id}/", params=params
            ),
        )

    def list(self, **filters: Any) -> AsyncResourceIterator:
        """List resources with optional filtering."""
        valid_filters = self.validate_filters(filters)
        return AsyncResourceIterator(self, valid_filters)
