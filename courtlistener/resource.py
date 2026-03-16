from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, Generic, TypeVar
from urllib.parse import urlparse

from courtlistener.models import Endpoint, Page
from courtlistener.utils import flatten_filters

if TYPE_CHECKING:
    from courtlistener.client import CourtListener


EndpointModelT = TypeVar("EndpointModelT", bound=Endpoint)


class ResourceIterator:
    """Iterator for paginated API results."""

    def __init__(
        self,
        resource: Resource[EndpointModelT],
        filters: dict[str, Any],
    ) -> None:
        self._client = resource._client
        self._endpoint = resource._endpoint
        self._filters = filters
        self._current_page: Page | None = None
        self._count: int | None = None
        self._index: int = 0

    def _fetch_page(self, url: str | None = None) -> Page:
        """Fetch a page of results."""
        if url:
            parsed = urlparse(url)
            path = parsed.path
            if parsed.query:
                path = f"{path}?{parsed.query}"
            data = self._client._request("GET", path)
        else:
            data = self._client._request(
                "GET", self._endpoint, params=self._filters
            )
        return Page(**data)

    @property
    def current_page(self) -> Page:
        """Get the current page."""
        if self._current_page is None:
            self._current_page = self._fetch_page()
        return self._current_page

    def has_next(self) -> bool:
        """Whether there is a next page."""
        return self.current_page.next is not None

    def has_previous(self) -> bool:
        """Whether there is a previous page."""
        return self.current_page.previous is not None

    def next(self) -> None:
        """Get the next page."""
        if not self.has_next():
            raise ValueError("No next page")
        self._current_page = self._fetch_page(self.current_page.next)

    def previous(self) -> None:
        """Get the previous page."""
        if not self.has_previous():
            raise ValueError("No previous page")
        self._current_page = self._fetch_page(self.current_page.previous)

    def __iter__(self) -> Iterator[dict[str, Any]]:
        """Iterate over all results across pages, respecting the current index."""
        yielded = 0
        while True:
            results = self.current_page.results
            page_size = len(results)
            if yielded + page_size <= self._index:
                # Skip this entire page
                yielded += page_size
                if not self.has_next():
                    break
                self.next()
                continue
            # Yield results from the offset within this page
            start = self._index - yielded
            for item in results[start:]:
                self._index += 1
                yield item
            yielded = self._index
            if not self.has_next():
                break
            self.next()

    @property
    def count(self) -> int:
        """Total count of results across all pages."""
        if self._count is None:
            if self.current_page.count is None:
                raise ValueError("No count URL")
            elif isinstance(self.current_page.count, int):
                self._count = self.current_page.count
            else:
                parsed = urlparse(self.current_page.count)
                path = parsed.path
                if parsed.query:
                    path = f"{path}?{parsed.query}"
                data = self._client._request("GET", path)
                self._count = int(data.get("count", 0))
        return self._count

    @property
    def document_count(self) -> int | None:
        """Total count of nested documents for recap search endpoint."""
        if self.current_page is not None:
            return self.current_page.document_count
        return None

    @property
    def results(self) -> list[dict[str, Any]]:
        """Results from the current page."""
        return self.current_page.results

    def dump(self) -> dict[str, Any]:
        """Serialize the iterator state to a dict for later restoration."""
        return {
            "current_page": self.current_page.model_dump(),
            "filters": self._filters,
            "endpoint": self._endpoint,
            "index": self._index,
            "count": self._count,
        }

    @classmethod
    def load(
        cls, client: CourtListener, data: dict[str, Any]
    ) -> ResourceIterator:
        """Restore a ResourceIterator from a previously dumped state."""
        iterator = cls.__new__(cls)
        iterator._client = client
        iterator._endpoint = data["endpoint"]
        iterator._filters = data["filters"]
        iterator._current_page = Page(**data["current_page"])
        iterator._index = data["index"]
        iterator._count = data["count"]
        return iterator


class Resource(Generic[EndpointModelT]):
    """Resource class for API endpoints."""

    def __init__(
        self, client: CourtListener, model: type[EndpointModelT]
    ) -> None:
        self._client = client
        self._model = model
        self._endpoint = model.endpoint

    def validate_filters(self, filters: dict[str, Any]) -> dict[str, Any]:
        filters = self._model(**filters).model_dump(by_alias=True)
        filters = flatten_filters(filters)
        filters = {k: v for k, v in filters.items() if v is not None}
        return filters

    def get(self, id: int | str) -> dict[str, Any]:
        """Get a resource by its ID."""
        return self._client._request("GET", f"{self._endpoint}{id}/")

    def list(self, **filters: Any) -> ResourceIterator:
        """List resources with optional filtering."""
        valid_filters = self.validate_filters(filters)
        return ResourceIterator(self, valid_filters)
