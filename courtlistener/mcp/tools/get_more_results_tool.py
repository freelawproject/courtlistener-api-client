from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.utils import (
    DEFAULT_NUM_RESULTS,
    MAX_NUM_RESULTS,
    collect_results,
    filter_results_by_fields,
    get_session_query,
    has_more_results,
    prepare_has_more_str,
    store_session_query,
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

    async def __call__(self, arguments: dict, ctx: Context) -> str | dict:
        query_id = arguments["query_id"]
        num_results = arguments.get("num_results", DEFAULT_NUM_RESULTS)

        with self.get_client() as client:
            query = await get_session_query(query_id, client)
            if query is None:
                raise ValueError(
                    f"Query ID {query_id!r} not found. The session may have "
                    "expired, please redo the query first."
                )

            response = ResourceIterator.load(client, query["response"])

            if not has_more_results(response):
                return f"No more results available for query {query_id!r}."

            results = collect_results(response, num_results)

            updated_data = {"response": response.dump()}
            fields = query.get("fields")
            if fields is not None:
                updated_data["fields"] = fields
            await store_session_query(query_id, updated_data, client)

            filtered_results, _ = filter_results_by_fields(results, fields)

            outputs = {
                "query_id": query_id,
                "results": filtered_results,
            }

            has_more_str = prepare_has_more_str(response, query_id)
            if has_more_str is not None:
                outputs["has_more"] = has_more_str

            return outputs
