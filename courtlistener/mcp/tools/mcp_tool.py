from __future__ import annotations

import hashlib

from mcp.types import CallToolResult, Tool

from courtlistener import CourtListener
from courtlistener.mcp.auth import request_api_token


class MCPTool:
    name: str | None = None

    def get_client(self) -> CourtListener:
        """Get a CourtListener client with the appropriate API token.

        Token resolution:
        - HTTP mode: reads from ContextVar (set by AuthMiddleware
          from the Authorization header)
        - stdio mode: falls back to COURTLISTENER_API_TOKEN env var
          (handled by CourtListener constructor)
        """
        token = request_api_token.get()
        if token:
            return CourtListener(api_token=token)
        return CourtListener()

    def get_user_id(self) -> str:
        """Derive a user identifier for session key scoping.

        HTTP mode: truncated SHA-256 of the API token.
        stdio mode: fixed ``"local"`` identifier.
        """
        token = request_api_token.get()
        if token:
            return hashlib.sha256(token.encode()).hexdigest()[:16]
        return "local"

    def get_tool(self) -> Tool:
        if self.name is None:
            raise ValueError("name must be set")
        return Tool(
            name=self.name,
            description=self.get_description(),
            inputSchema=self.get_input_schema(),
        )

    def get_description(self) -> str:
        return self.__doc__ or ""

    def get_input_schema(self) -> dict:
        raise NotImplementedError(
            "get_input_schema must be implemented by subclass"
        )

    def __call__(
        self, arguments: dict, session: dict
    ) -> CallToolResult:
        raise NotImplementedError(
            "__call__ must be implemented by subclass"
        )
