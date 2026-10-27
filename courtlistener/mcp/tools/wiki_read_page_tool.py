from mcp.types import ToolAnnotations

from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.utils import wiki_get


class WikiReadPageTool(MCPTool):
    """Read one Free Law Project wiki page as Markdown.

    `path` is the page's path from `wiki_list_pages` or `wiki_search`,
    e.g. `engineering/deploys`; it is also the tail of the page's
    wiki.free.law/c/... URL.
    """

    name: str = "wiki_read_page"
    annotations: ToolAnnotations = ToolAnnotations(
        title="Read Wiki Page",
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The page path, e.g. `engineering/deploys`.",
                }
            },
            "required": ["path"],
            "additionalProperties": False,
        }

    async def call(self, arguments: dict) -> dict:
        return await wiki_get(f"pages/{arguments['path'].strip('/')}")
