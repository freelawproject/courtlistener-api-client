"""Authentication utilities for the remote MCP server.

Supports two auth modes (checked in order):

1. **OAuth Bearer token** — ``Authorization: Bearer <token>``.
   The token is validated against an OAuth introspection endpoint
   (RFC 7662) which returns the user's CL API token.

2. **Direct CL token** — ``Authorization: Token <token>``.
   The token is passed through to the CourtListener API as-is.

A Starlette middleware extracts the resolved CL API token and stores
it in a ``contextvars.ContextVar`` so that tool handlers can retrieve
it without changes to the MCP protocol layer.
"""

from __future__ import annotations

import contextvars
import logging
import os

import httpx
from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint,
)
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Holds the CL API token for the current request.
# Set by AuthMiddleware, read by MCPTool.get_client().
request_api_token: contextvars.ContextVar[str | None] = (
    contextvars.ContextVar("request_api_token", default=None)
)

# URL of the OAuth introspection endpoint (Stage 2).
# When set, Bearer tokens are validated against this endpoint.
OAUTH_INTROSPECTION_URL = os.environ.get("OAUTH_INTROSPECTION_URL")


class AuthMiddleware(BaseHTTPMiddleware):
    """Resolve the CL API token from the Authorization header.

    Supports both ``Token <cl-token>`` (direct passthrough) and
    ``Bearer <oauth-token>`` (introspected to get the CL token).
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        token = await _resolve_token(request)
        reset_token = request_api_token.set(token)
        try:
            return await call_next(request)
        finally:
            request_api_token.reset(reset_token)


async def _resolve_token(request: Request) -> str | None:
    """Extract and resolve the CL API token from the request."""
    auth = request.headers.get("authorization", "")

    # Stage 1: Direct CL token passthrough
    if auth.lower().startswith("token "):
        return auth[len("token ") :].strip()

    # Stage 2: OAuth Bearer token → introspect to get CL token
    if auth.lower().startswith("bearer ") and OAUTH_INTROSPECTION_URL:
        bearer = auth[len("bearer ") :].strip()
        return await _introspect_bearer(bearer)

    return None


async def _introspect_bearer(bearer_token: str) -> str | None:
    """Call the OAuth introspection endpoint to validate a Bearer token
    and retrieve the associated CL API token.

    Returns the CL API token if the Bearer token is active, else None.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                OAUTH_INTROSPECTION_URL,
                data={"token": bearer_token},
                timeout=5.0,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.exception("OAuth introspection failed")
        return None

    if not data.get("active"):
        return None

    return data.get("cl_api_token")
