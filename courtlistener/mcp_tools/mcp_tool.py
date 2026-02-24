from mcp.types import CallToolResult, TextContent, Tool

from courtlistener import CourtListener


class MCPTool:
    name: str | None = None

    def get_client(self) -> CourtListener:
        return CourtListener()

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
    ) -> list[TextContent] | CallToolResult:
        raise NotImplementedError("__call__ must be implemented by subclass")
