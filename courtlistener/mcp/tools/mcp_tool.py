from __future__ import annotations

from typing import Any

from fastmcp.server.context import Context
from fastmcp.server.dependencies import get_http_request
from fastmcp.tools import Tool
from mcp.types import ToolAnnotations

from courtlistener import CourtListener


class MCPTool:
    name: str | None = None
    annotations: ToolAnnotations | None = None

    def get_client(self) -> CourtListener:
        """Get a CourtListener client with the appropriate API token.

        Token resolution:
        - HTTP mode: reads from ContextVar (set by AuthMiddleware
          from the Authorization header)
        - stdio mode: falls back to COURTLISTENER_API_TOKEN env var
          (handled by CourtListener constructor)
        """
        request = get_http_request()
        auth = request.headers.get("Authorization")

        token = None
        if auth is not None and auth.startswith("Token "):
            token = auth[len("Token ") :] or None

        if token:
            return CourtListener(api_token=token)
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
