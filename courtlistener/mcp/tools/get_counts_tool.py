from mcp.types import CallToolResult, TextContent, ToolAnnotations

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.resource import ResourceIterator


class GetCountsTool(MCPTool):
    """Get the number of results from a previous query.

    Some endpoints return the count lazily. Use this tool to retrieve the count
    from a previous query if it is not available.
    """

    name: str = "get_counts"
    annotations = ToolAnnotations(
        title="Getting Result Count",
        readOnlyHint=True,
        openWorldHint=True,
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query_id": {
                    "type": "integer",
                    "description": "The search ID to get the count from.",
                },
            },
            "required": ["query_id"],
        }

    def __call__(self, arguments: dict, session: dict) -> CallToolResult:
        with self.get_client() as client:
            query_id = arguments["query_id"]
            data = session.get("queries", {}).get(query_id)
            if data is None:
                return CallToolResult(
                    content=[
                        TextContent(
                            type="text",
                            text=(
                                f"Query ID {query_id} not found. "
                                "The session may have expired, please redo the query first."
                            ),
                        )
                    ],
                    isError=True,
                )
            response = ResourceIterator.load(client, data["response"])
            try:
                count = response.count
            except (ValueError, CourtListenerAPIError) as exc:
                return CallToolResult(
                    content=[TextContent(type="text", text=str(exc))],
                    isError=True,
                )
            return CallToolResult(
                content=[TextContent(type="text", text=str(count))]
            )
