import os
from typing import Any

import httpx

from courtlistener.models import ENDPOINTS
from courtlistener.resource import Resource

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
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
        return self._http_client

    def close(self) -> None:
        """Close the HTTP client."""
        if self._http_client is not None:
            self._http_client.close()
            self._http_client = None

    def __enter__(self) -> "CourtListener":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _request(
        self, method: str, path: str, **kwargs: Any
    ) -> dict[str, Any]:
        """Make an HTTP request to the API.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API endpoint path
            **kwargs: Additional arguments to pass to httpx

        Returns:
            JSON response as a dictionary
        """

        overlap = max(
            i for i in range(len(path)) if self.base_url.endswith(path[:i])
        )
        if overlap:
            path = path[overlap:]
        response = self.client.request(method, path, **kwargs)
        response.raise_for_status()
        return dict(response.json())
