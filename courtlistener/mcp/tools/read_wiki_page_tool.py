import httpx
from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.wiki_api import wiki_get


class ReadWikiPageTool(MCPTool):
    """Read one Free Law wiki page as markdown.

    Takes a page ``path`` as returned by ``list_wiki_pages`` or
    ``search_wiki`` (e.g. ``courtlistener/help/api/rest-api``) and
    returns the page's title, canonical URL, and full markdown content.
    Renamed pages are followed through their redirects automatically.
    """

    name: str = "read_wiki_page"
    annotations = ToolAnnotations(
        title="Read Wiki Page",
        readOnlyHint=True,
        destructiveHint=False,
        openWorldHint=True,
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "The page path from list_wiki_pages or "
                        "search_wiki results."
                    ),
                },
            },
            "required": ["path"],
        }

    async def __call__(self, arguments: dict, ctx: Context) -> dict:
        path = arguments["path"].strip().strip("/")
        try:
            return await wiki_get(f"/api/v1/pages/{path}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
            # The wiki intentionally answers missing and forbidden
            # paths identically, so don't claim to know which it is.
            raise ValueError(
                f"No wiki page at {path!r} — or you don't have access "
                "to it. Check the path with list_wiki_pages or "
                "search_wiki."
            ) from exc
