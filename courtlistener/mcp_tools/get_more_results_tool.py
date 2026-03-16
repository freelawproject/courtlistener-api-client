import json

from mcp.types import CallToolResult, TextContent

from courtlistener.mcp_tools.mcp_tool import MCPTool
from courtlistener.mcp_tools.utils import (
    DEFAULT_NUM_RESULTS,
    MAX_NUM_RESULTS,
    collect_results,
    has_more_results,
    prepare_has_more_str,
)
from courtlistener.resource import ResourceIterator


class GetMoreResultsTool(MCPTool):
    """Get more results from a previous query.

    Use this tool to continue paginating through results returned by the
    `search` or `call_endpoint` tools.
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
                        f"Number of results to return (1-{MAX_NUM_RESULTS}). "
                        f"Defaults to {DEFAULT_NUM_RESULTS}."
                    ),
                    "minimum": 1,
                    "maximum": MAX_NUM_RESULTS,
                    "default": DEFAULT_NUM_RESULTS,
                },
            },
            "required": ["query_id"],
        }

    def __call__(self, arguments: dict, session: dict) -> CallToolResult:
        query_id = arguments["query_id"]
        num_results = arguments.get("num_results", DEFAULT_NUM_RESULTS)

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

        with self.get_client() as client:
            response = ResourceIterator.load(client, data)

            if not has_more_results(response):
                return CallToolResult(
                    content=[
                        TextContent(
                            type="text",
                            text=f"No more results available for query {query_id}.",
                        )
                    ]
                )

            results = collect_results(response, num_results)

            # Update the stored state with the new page_result_index.
            session["queries"][query_id] = response.dump()

            outputs = [f"Query ID: {query_id}"]
            results_str = json.dumps(results, indent=2)
            outputs.append(results_str)

            has_more_str = prepare_has_more_str(response, query_id)
            outputs.append(has_more_str)

            outputs_str = "\n\n".join([x for x in outputs if x]).strip()
            return CallToolResult(
                content=[TextContent(type="text", text=outputs_str)]
            )
