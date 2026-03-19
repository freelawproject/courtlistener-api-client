from mcp.types import CallToolResult, Tool

from courtlistener import CourtListener
from courtlistener.mcp.auth import request_api_token


class MCPTool:
    name: str | None = None

    def get_client(self, session: dict | None = None) -> CourtListener:
        # Priority: HTTP header token > session token > env var (in CourtListener.__init__)
        token = request_api_token.get(None)
        if not token and session:
            token = session.get("api_token")
        return CourtListener(api_token=token) if token else CourtListener()

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

    def __call__(self, arguments: dict, session: dict) -> CallToolResult:
        raise NotImplementedError("__call__ must be implemented by subclass")
