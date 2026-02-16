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
        resource: "Resource[EndpointModelT]",
        filters: dict[str, Any],
    ) -> None:
        self._resource = resource
        self._filters = filters
        self._current_page: Page | None = None
        self._count: int | None = None

    def _fetch_page(self, url: str | None = None) -> Page:
        """Fetch a page of results."""
        if url:
            parsed = urlparse(url)
            path = parsed.path
            if parsed.query:
                path = f"{path}?{parsed.query}"
            data = self._resource._client._request("GET", path)
        else:
            data = self._resource._client._request(
                "GET", self._resource._endpoint, params=self._filters
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
        """Iterate over all results across pages."""
        while True:
            yield from self.current_page.results
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
                data = self._resource._client._request("GET", path)
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


class Resource(Generic[EndpointModelT]):
    """Resource class for API endpoints."""

    def __init__(
        self, client: "CourtListener", model: type[EndpointModelT]
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
