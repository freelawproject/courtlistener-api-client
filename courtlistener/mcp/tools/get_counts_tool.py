from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.utils import get_session_query
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
                    "type": "string",
                    "description": (
                        "The query ID (short UUID) to get the count from."
                    ),
                },
            },
            "required": ["query_id"],
        }

    async def __call__(self, arguments: dict, ctx: Context) -> dict[str, int]:
        query_id = arguments["query_id"]
        with self.get_client() as client:
            data = await get_session_query(query_id, client)
            if data is None:
                raise ValueError(
                    f"Query ID {query_id!r} not found. The session may have "
                    "expired, please redo the query first."
                )
            response = ResourceIterator.load(client, data["response"])
            count = response.count
            return {"count": count}
