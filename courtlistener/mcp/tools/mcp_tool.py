from __future__ import annotations

from typing import Any

from fastmcp.server.context import Context
from fastmcp.server.dependencies import get_access_token, get_http_request
from fastmcp.tools import Tool
from mcp.types import ToolAnnotations

from courtlistener import CourtListener


class MCPTool:
    name: str | None = None
    annotations: ToolAnnotations | None = None

    def get_client(self) -> CourtListener:
        """Build a CourtListener client for the current request.

        Resolution order:
        1. HTTP + OAuth mode: use the OAuth access token FastMCP
           validated against CL's JWKS. Forwarded to the CL API as
           ``Authorization: Bearer <jwt>``, which CL accepts because
           ``OAuth2Authentication`` is registered in its
           ``DEFAULT_AUTHENTICATION_CLASSES``.
        2. HTTP + legacy mode: ``Authorization: Token <api_token>``
           header (existing stdio-over-HTTP / testing path).
        3. stdio mode: ``COURTLISTENER_API_TOKEN`` env var, resolved
           by the ``CourtListener`` constructor.
        """
        # 1. OAuth bearer token (HTTP + JWTVerifier active)
        access_token = get_access_token()
        if access_token is not None:
            return CourtListener(access_token=access_token.token)

        # 2. Legacy "Token ..." header pass-through (no OAuth).
        #    get_http_request() raises when called outside an HTTP
        #    request (e.g. stdio mode), so guard against that.
        try:
            request = get_http_request()
        except RuntimeError:
            request = None
        if request is not None:
            auth = request.headers.get("Authorization")
            if auth and auth.startswith("Token "):
                return CourtListener(api_token=auth[len("Token ") :] or None)

        # 3. stdio mode — env var
        return CourtListener()

    def get_tool(self) -> Tool:
        if self.name is None:
            raise ValueError("name must be set")
        if self.annotations is None:
            raise ValueError("annotations must be set")
        return Tool(
            name=self.name,
            description=self.get_description(),
            parameters=self.get_input_schema(),
            annotations=self.annotations,
        )

    def get_description(self) -> str:
        return self.__doc__ or ""

    def get_input_schema(self) -> dict:
        raise NotImplementedError(
            "get_input_schema must be implemented by subclass"
        )

    async def __call__(self, arguments: dict, ctx: Context) -> Any:
        raise NotImplementedError("__call__ must be implemented by subclass")
