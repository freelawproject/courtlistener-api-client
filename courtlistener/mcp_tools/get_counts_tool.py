from mcp.types import CallToolResult, TextContent

from courtlistener.mcp_tools.mcp_tool import MCPTool


class GetCountsTool(MCPTool):
    """Get the number of results from a previous query.

    Some endpoints return the count lazily. Use this tool to retrieve the count
    from a previous query if it is not available.
    """

    name: str = "get_counts"

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
            query = session["queries"].get(query_id)
            if query is None:
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
            count_url = query.get("count")
            if count_url is None:
                return CallToolResult(
                    content=[
                        TextContent(
                            type="text",
                            text=(
                                f"Query ID {query_id} does not have a count URL. "
                                "The session may have expired, please redo the query first."
                            ),
                        )
                    ],
                    isError=True,
                )
            response = client._request("GET", count_url)
            count = response.get("count")
            if count is None:
                return CallToolResult(
                    content=[TextContent(type="text", text="No count found")],
                    isError=True,
                )
            return CallToolResult(
                content=[TextContent(type="text", text=str(count))]
            )
