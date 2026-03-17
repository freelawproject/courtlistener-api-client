from __future__ import annotations

from typing import Any

import httpx


class CourtListenerAPIError(Exception):
    """Raised when the CourtListener API returns an error response.

    Attributes:
        status_code: The HTTP status code of the response.
        detail: Parsed JSON body if available, otherwise raw response text.
        response: The original ``httpx.Response`` object.
    """

    def __init__(
        self,
        status_code: int,
        detail: Any,
        response: httpx.Response,
    ) -> None:
        self.status_code = status_code
        self.detail = detail
        self.response = response

        super().__init__(f"HTTP {status_code}: {detail}")
