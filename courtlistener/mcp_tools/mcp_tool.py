from mcp.types import CallToolResult, Tool

from courtlistener import CourtListener


class MCPTool:
    name: str | None = None

    def get_client(self) -> CourtListener:
        return CourtListener()

    def get_or_create_client(self, session: dict) -> CourtListener:
        """Get a persistent client from the session, or create one.

        Use this instead of get_client() when the resulting
        ResourceIterator needs to survive beyond the tool call
        (e.g. for pagination or deferred count resolution).
        """
        if "client" not in session:
            session["client"] = CourtListener()
        return session["client"]

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
