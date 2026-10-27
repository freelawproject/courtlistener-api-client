from mcp.types import ToolAnnotations

from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.utils import wiki_get


class WikiListPagesTool(MCPTool):
    """List the Free Law Project wiki pages you can read.

    Returns each page's path, title and description. Public pages are
    always listed; pages for FLP staff and pages shared with you appear
    when your CourtListener account's email has access to them on the
    wiki. Pass a path to `wiki_read_page` to read a page.
    """

    name: str = "wiki_list_pages"
    annotations: ToolAnnotations = ToolAnnotations(
        title="List Wiki Pages",
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

    async def call(self, arguments: dict) -> dict:
        return await wiki_get("pages/")
