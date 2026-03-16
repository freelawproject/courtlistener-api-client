import json

from mcp.types import CallToolResult, TextContent

from courtlistener.mcp_tools.mcp_tool import MCPTool
from courtlistener.mcp_tools.utils import collect_results

MAX_NUM_RESULTS = 100
DEFAULT_NUM_RESULTS = 20


class GetMoreResultsTool(MCPTool):
    """Get more results from a previous search or endpoint query.

    Use this tool to paginate through results from a previous
    `search` or `call_endpoint` query.
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
                    "description": (
                        f"Number of additional results to return (default {DEFAULT_NUM_RESULTS}, "
                        f"max {MAX_NUM_RESULTS})."
                    ),
                },
            },
            "required": ["query_id"],
        }

    def __call__(self, arguments: dict, session: dict) -> CallToolResult:
        query_id = arguments["query_id"]
        num_results = min(
            max(arguments.get("num_results", DEFAULT_NUM_RESULTS), 1),
            MAX_NUM_RESULTS,
        )

        query_entry = session.get("queries", {}).get(query_id)
        if query_entry is None:
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

        results = collect_results(query_entry, num_results)
        if not results:
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=(
                            f"No more results available for query {query_id}. "
                            f"Total results returned: {query_entry['returned_count']}."
                        ),
                    )
                ],
            )

        outputs = [
            f"Query ID: {query_id}",
            f"Results {query_entry['returned_count'] - len(results) + 1}"
            f"-{query_entry['returned_count']}",
            json.dumps(results, indent=2),
        ]

        if len(results) == num_results:
            outputs.append(
                f"Use `get_more_results` with query_id={query_id} "
                f"to retrieve additional results."
            )

        outputs_str = "\n\n".join(outputs)
        return CallToolResult(
            content=[TextContent(type="text", text=outputs_str)]
        )
