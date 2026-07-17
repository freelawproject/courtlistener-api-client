from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.wiki_api import wiki_get


class ListWikiPagesTool(MCPTool):
    """List documentation pages on the Free Law wiki.

    The wiki (wiki.free.law) documents CourtListener, its APIs, this
    MCP server, and Free Law Project's other tools and data. Returns
    every page the current user can read — public pages for everyone,
    plus internal pages when signed in with an account the wiki
    recognizes. Each entry includes the ``path`` to pass to
    ``read_wiki_page``.

    Prefer ``search_wiki`` when looking for something specific; use
    this to browse or to get the lay of the land.
    """

    name: str = "list_wiki_pages"
    annotations = ToolAnnotations(
        title="List Wiki Pages",
        readOnlyHint=True,
        destructiveHint=False,
        openWorldHint=True,
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": (
                        "Optional directory path (e.g. "
                        "'courtlistener/help/api') to limit the listing "
                        "to that directory and its descendants."
                    ),
                },
            },
        }

    async def __call__(self, arguments: dict, ctx: Context) -> dict:
        params = {}
        if directory := arguments.get("directory"):
            params["directory"] = directory
        return await wiki_get("/api/v1/pages/", params=params)
