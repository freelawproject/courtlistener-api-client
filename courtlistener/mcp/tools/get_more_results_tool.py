from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from courtlistener.async_client.resource import AsyncResourceIterator
from courtlistener.mcp.exceptions import SessionDataNotFoundError
from courtlistener.mcp.session import get_session
from courtlistener.mcp.settings import (
    DEFAULT_NUM_RESULTS,
    MAX_NUM_RESULTS,
)
from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.utils import (
    add_opinion_ids,
    collect_results,
    filter_results_by_fields,
    has_more_results,
    normalize_fields,
    prepare_has_more_str,
)


class GetMoreResultsTool(MCPTool):
    """Get more results from a previous query.

    Use this tool to continue paginating through results returned by the
    `search` or `call_endpoint` tools.
    """

    name: str = "get_more_results"
    annotations = ToolAnnotations(
        title="Get More Results",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
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
            "additionalProperties": False,
        }

    async def __call__(self, arguments: dict, ctx: Context) -> str | dict:
        query_id = arguments["query_id"]
        num_results = arguments.get("num_results", DEFAULT_NUM_RESULTS)

        async with self.get_client() as client:
            query = await get_session().get_query(query_id, client)
            if query is None:
                raise SessionDataNotFoundError(
                    f"Query ID {query_id!r} not found. The session may have "
                    "expired, please redo the query first.",
                    tool_name=self.name,
                    argument_name="query_id",
                )

            response = AsyncResourceIterator.load(client, query["response"])

            if not await has_more_results(response):
                return f"No more results available for query {query_id!r}."

            results = await collect_results(response, num_results)
            add_opinion_ids(results)

            updated_data = {"response": await response.dump()}
            fields = query.get("fields")
            if fields is not None:
                updated_data["fields"] = fields
            await get_session().store_query(query_id, updated_data, client)

            filtered_results, _ = filter_results_by_fields(
                results, normalize_fields(fields)
            )

            outputs = {
                "query_id": query_id,
                "results": filtered_results,
            }

            has_more_str = await prepare_has_more_str(response, query_id)
            if has_more_str is not None:
                outputs["has_more"] = has_more_str

            return outputs
