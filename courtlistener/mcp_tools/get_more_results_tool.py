import json

from mcp.types import CallToolResult, TextContent

from courtlistener.mcp_tools.mcp_tool import MCPTool
from courtlistener.mcp_tools.utils import collect_results


class GetMoreResultsTool(MCPTool):
    """Get additional results from a previous search or endpoint query.

    Use this tool to paginate through results by referencing the query_id
    returned by a previous `search` or `call_endpoint` call.
    """

    name: str = "get_more_results"

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query_id": {
                    "type": "integer",
                    "description": "The query ID from a previous search or call_endpoint result.",
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of additional results to return (1-100).",
                    "default": 20,
                    "minimum": 1,
                    "maximum": 100,
                },
            },
            "required": ["query_id"],
        }

    def __call__(self, arguments: dict, session: dict) -> CallToolResult:
        query_id = arguments["query_id"]
        num_results = min(arguments.get("num_results", 20), 100)

        query = session.get("queries", {}).get(query_id)
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

        results = collect_results(session, query_id, num_results)

        if not results:
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=f"No more results available for query {query_id}.",
                    )
                ]
            )

        outputs = [
            f"Query ID: {query_id}",
            f"Returned {len(results)} additional result(s).",
            json.dumps(results, indent=2),
        ]
        outputs_str = "\n\n".join(outputs)
        return CallToolResult(
            content=[TextContent(type="text", text=outputs_str)]
        )
