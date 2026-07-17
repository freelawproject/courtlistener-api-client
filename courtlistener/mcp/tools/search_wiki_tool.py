from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.wiki_api import wiki_get


class SearchWikiTool(MCPTool):
    """Full-text search of the Free Law wiki.

    Searches wiki.free.law — documentation for CourtListener, its REST
    API, this MCP server, RECAP, and Free Law Project's other tools —
    and returns the top matches with highlighted snippets and paths to
    pass to ``read_wiki_page``. Results are scoped to what the current
    user can read.

    Supports the wiki's advanced query syntax: quoted phrases
    (``"docket alerts"``), ``title:`` terms, ``in:`` directory filters,
    ``before:``/``after:`` date filters, and ``-word`` exclusions.
    """

    name: str = "search_wiki"
    annotations = ToolAnnotations(
        title="Search the Wiki",
        readOnlyHint=True,
        destructiveHint=False,
        openWorldHint=True,
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query.",
                },
            },
            "required": ["query"],
        }

    async def __call__(self, arguments: dict, ctx: Context) -> dict:
        return await wiki_get(
            "/api/v1/search/", params={"q": arguments["query"]}
        )
