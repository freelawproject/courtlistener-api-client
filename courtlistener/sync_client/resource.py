from __future__ import annotations

import warnings
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlparse

from courtlistener.models import Endpoint, Page
from courtlistener.utils import flatten_filters, validate_model_fields

if TYPE_CHECKING:
    from courtlistener.sync_client.client import CourtListener


class ResourceIterator:
    """Iterator for paginated API results."""

    def __init__(
        self,
        resource: Resource,
        filters: dict[str, Any],
    ) -> None:
        self._client = resource._client
        self._endpoint = resource._endpoint
        self._filters = filters
        self._current_page: Page | None = None
        self._count: int | None = None
        self._page_result_index: int = 0

    def _fetch_page(self, url: str | None = None) -> Page:
        """Fetch a page of results."""
        if url:
            parsed = urlparse(url)
            path = parsed.path
            if parsed.query:
                path = f"{path}?{parsed.query}"
            data = cast(dict[str, Any], self._client._request("GET", path))
        else:
            data = cast(
                dict[str, Any],
                self._client._request(
                    "GET", self._endpoint, params=self._filters
                ),
            )
        return Page(**data)

    def get_current_page(self) -> Page:
        """Get the current page."""
        if self._current_page is None:
            self._current_page = self._fetch_page()
        return self._current_page

    def has_next(self) -> bool:
        """Whether there is a next page."""
        return self.get_current_page().next is not None

    def has_previous(self) -> bool:
        """Whether there is a previous page."""
        return self.get_current_page().previous is not None

    def next(self) -> None:
        """Get the next page."""
        if not self.has_next():
            raise ValueError("No next page")
        current_page = self.get_current_page()
        self._current_page = self._fetch_page(current_page.next)
        self._page_result_index = 0

    def previous(self) -> None:
        """Get the previous page."""
        if not self.has_previous():
            raise ValueError("No previous page")
        current_page = self.get_current_page()
        self._current_page = self._fetch_page(current_page.previous)
        self._page_result_index = 0

    def __iter__(self) -> Iterator[dict[str, Any]]:
        """Iterate over all results across pages, respecting the page result index."""
        while True:
            current_page = self.get_current_page()
            for item in current_page.results[self._page_result_index :]:
                self._page_result_index += 1
                yield item
            if not self.has_next():
                break
            self.next()

    def get_count(self) -> int:
        """Total count of results across all pages."""
        if self._count is None:
            current_page = self.get_current_page()
            if current_page.count is None:
                raise ValueError("No count URL")
            elif isinstance(current_page.count, int):
                self._count = current_page.count
            else:
                parsed = urlparse(current_page.count)
                path = parsed.path
                if parsed.query:
                    path = f"{path}?{parsed.query}"
                data = cast(dict[str, Any], self._client._request("GET", path))
                self._count = int(data.get("count", 0))
        return self._count

    def get_document_count(self) -> int | None:
        """Total count of nested documents for recap search endpoint."""
        current_page = self.get_current_page()
        if current_page is not None:
            return current_page.document_count
        return None

    def get_results(self) -> list[dict[str, Any]]:
        """Results from the current page."""
        return self.get_current_page().results

    def dump(self) -> dict[str, Any]:
        """Serialize the iterator state to a dict for later restoration."""
        current_page = self.get_current_page()
        return {
            "current_page": current_page.model_dump(),
            "filters": self._filters,
            "endpoint": self._endpoint,
            "page_result_index": self._page_result_index,
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
        iterator._page_result_index = data["page_result_index"]
        iterator._count = data["count"]
        return iterator

    # ------------------------------------------------------------------
    # Deprecated property aliases.
    #
    # Kept only for backwards compatibility with pre-async-split code;
    # they do not exist on AsyncResourceIterator and will not survive
    # the planned unasync code generation. Use the get_* methods.
    # ------------------------------------------------------------------

    def _warn_deprecated(self, name: str) -> None:
        warnings.warn(
            f"ResourceIterator.{name} is deprecated and will be removed "
            f"in a future release; use get_{name}() instead.",
            DeprecationWarning,
            stacklevel=3,
        )

    @property
    def current_page(self) -> Page:
        """Deprecated alias for :meth:`get_current_page`."""
        self._warn_deprecated("current_page")
        return self.get_current_page()

    @property
    def count(self) -> int:
        """Deprecated alias for :meth:`get_count`."""
        self._warn_deprecated("count")
        return self.get_count()

    @property
    def document_count(self) -> int | None:
        """Deprecated alias for :meth:`get_document_count`."""
        self._warn_deprecated("document_count")
        return self.get_document_count()

    @property
    def results(self) -> list[dict[str, Any]]:
        """Deprecated alias for :meth:`get_results`."""
        self._warn_deprecated("results")
        return self.get_results()


class Resource:
    """Resource class for API endpoints."""

    def __init__(
        self,
        client: CourtListener,
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

    def get(
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
            self._client._request(
                "GET", f"{self._endpoint}{id}/", params=params
            ),
        )

    def list(self, **filters: Any) -> ResourceIterator:
        """List resources with optional filtering."""
        valid_filters = self.validate_filters(filters)
        return ResourceIterator(self, valid_filters)
