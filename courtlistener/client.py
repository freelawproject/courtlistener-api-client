from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import httpx

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.models import ENDPOINTS
from courtlistener.resource import Resource

if TYPE_CHECKING:
    from courtlistener.alerts import DocketAlerts, SearchAlerts
    from courtlistener.citation_lookup import CitationLookup

DEFAULT_BASE_URL = "https://www.courtlistener.com/api/rest/v4"


class CourtListener:
    """Client for interacting with the CourtListener API."""

    def __init__(
        self,
        api_token: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 300.0,
    ) -> None:
        """Initialize the CourtListener client.

        Args:
            api_token: CourtListener API token. If not provided, will look for
                COURTLISTENER_API_TOKEN environment variable.
            base_url: Base URL for the CourtListener API.
            timeout: Request timeout in seconds.
        """
        self.api_token = api_token or os.environ.get("COURTLISTENER_API_TOKEN")
        if not self.api_token:
            raise ValueError(
                "API token is required. Provide it directly or set COURTLISTENER_API_TOKEN "
                "environment variable."
            )

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._http_client: httpx.Client | None = None
        self._resources: dict[str, Resource[Any]] = {}

    @property
    def alerts(self) -> SearchAlerts:
        """Access the search alerts API."""
        if not hasattr(self, "_alerts"):
            from courtlistener.alerts import SearchAlerts

            self._alerts = SearchAlerts(self)
        return self._alerts

    @property
    def docket_alerts(self) -> DocketAlerts:
        """Access the docket alerts API."""
        if not hasattr(self, "_docket_alerts"):
            from courtlistener.alerts import DocketAlerts

            self._docket_alerts = DocketAlerts(self)
        return self._docket_alerts

    @property
    def citation_lookup(self) -> CitationLookup:
        """Access the citation lookup and verification API."""
        if not hasattr(self, "_citation_lookup"):
            from courtlistener.citation_lookup import CitationLookup

            self._citation_lookup = CitationLookup(self)
        return self._citation_lookup

    def __getattr__(self, name: str) -> Resource[Any]:
        """Dynamically create resource accessors based on registered endpoints."""
        if not name.startswith("_"):
            if name in self._resources:
                return self._resources[name]

            if name in ENDPOINTS:
                resource: Resource[Any] = Resource(self, ENDPOINTS[name])
                self._resources[name] = resource
                return resource

        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )

    @property
    def client(self) -> httpx.Client:
        """Get or create the HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.Client(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Token {self.api_token}",
                },
                timeout=self.timeout,
            )
        return self._http_client

    def close(self) -> None:
        """Close the HTTP client."""
        if self._http_client is not None:
            self._http_client.close()
            self._http_client = None

    def __enter__(self) -> CourtListener:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _request(
        self, method: str, path: str, **kwargs: Any
    ) -> dict[str, Any] | list[Any]:
        """Make an HTTP request to the API.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API endpoint path
            **kwargs: Additional arguments to pass to httpx

        Returns:
            Parsed JSON response (dict or list)
        """

        overlap = max(
            i for i in range(len(path)) if self.base_url.endswith(path[:i])
        )
        if overlap:
            path = path[overlap:]
        response = self.client.request(method, path, **kwargs)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise CourtListenerAPIError(
                status_code=response.status_code,
                detail=detail,
                response=response,
            ) from None
        if response.status_code == 204:
            return {}
        return response.json()
