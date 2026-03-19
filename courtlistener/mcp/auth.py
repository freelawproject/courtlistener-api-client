"""Authentication utilities for the remote MCP server.

When running with Streamable HTTP transport, clients pass their
CourtListener API token via the ``Authorization`` header. A Starlette
middleware extracts the token and stores it in a ``contextvars.ContextVar``
so that tool handlers can retrieve it without changes to the MCP
protocol layer.
"""

from __future__ import annotations

import contextvars

from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint,
)
from starlette.requests import Request
from starlette.responses import Response

# Holds the API token for the current request. Set by AuthMiddleware,
# read by MCPTool.get_client().
request_api_token: contextvars.ContextVar[str | None] = (
    contextvars.ContextVar("request_api_token", default=None)
)


class AuthMiddleware(BaseHTTPMiddleware):
    """Extract CourtListener API token from the Authorization header.

    Accepts tokens in the format used by the CourtListener API::

        Authorization: Token <api-token>

    The token is stored in the ``request_api_token`` context variable
    for the duration of the request.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        token = _extract_token(request)
        reset_token = request_api_token.set(token)
        try:
            return await call_next(request)
        finally:
            request_api_token.reset(reset_token)


def _extract_token(request: Request) -> str | None:
    """Parse ``Authorization: Token <value>`` from the request."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("token "):
        return auth[len("token ") :].strip()
    return None
