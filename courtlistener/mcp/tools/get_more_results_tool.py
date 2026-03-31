import json

from mcp.types import CallToolResult, TextContent, ToolAnnotations

from courtlistener.mcp.session import SessionStore
from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.utils import (
    DEFAULT_NUM_RESULTS,
    MAX_NUM_RESULTS,
    collect_results,
    filter_fields,
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
    annotations = ToolAnnotations(
        title="Getting More Results",
        readOnlyHint=True,
        openWorldHint=True,
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query_id": {
                    "type": "string",
                    "description": (
                        "The query ID (short UUID) from a previous "
                        "search or call_endpoint result."
                    ),
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

    def __call__(
        self, arguments: dict, session: SessionStore
    ) -> CallToolResult:
        user_id = self.get_user_id()
        query_id = arguments["query_id"]
        num_results = arguments.get("num_results", DEFAULT_NUM_RESULTS)

        data = session.get_query(user_id, query_id)
        if data is None:
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=(
                            f"Query ID {query_id!r} not found. "
                            "The session may have expired, "
                            "please redo the query first."
                        ),
                    )
                ],
                isError=True,
            )

        with self.get_client() as client:
            response = ResourceIterator.load(client, data["response"])

            if not has_more_results(response):
                return CallToolResult(
                    content=[
                        TextContent(
                            type="text",
                            text=(
                                f"No more results available for "
                                f"query {query_id!r}."
                            ),
                        )
                    ]
                )

            results = collect_results(response, num_results)

            # Persist updated page cursor back to the session.
            # Conditionally include "fields" to stay consistent with
            # prepare_query_id, which omits the key when fields is None.
            session.store_query(
                user_id,
                query_id,
                {
                    "response": response.dump(),
                    **({
                        "fields": data["fields"]
                    } if "fields" in data else {}),
                },
            )

            fields = data.get("fields")
            filtered_results, _ = filter_fields(results, fields)

            outputs = [f"Query ID: {query_id}"]
            results_str = json.dumps(filtered_results, indent=2)
            outputs.append(results_str)

            has_more_str = prepare_has_more_str(response, query_id)
            outputs.append(has_more_str)

            outputs_str = "\n\n".join([x for x in outputs if x]).strip()
            return CallToolResult(
                content=[TextContent(type="text", text=outputs_str)]
            )
