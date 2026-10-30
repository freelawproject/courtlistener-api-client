from mcp.types import ToolAnnotations

from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.utils import wiki_get


class WikiSearchTool(MCPTool):
    """Search the Free Law Project wiki pages you can read.

    Full-text search over page titles and content. The query supports
    quoted phrases, `-word` to exclude a word, `title:word`, and
    `in:<directory path>` to search one directory. Each result carries a
    path for `wiki_read_page` and a snippet of the matching text.
    """

    name: str = "wiki_search"
    annotations: ToolAnnotations = ToolAnnotations(
        title="Search Wiki",
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "The search query."}
            },
            "required": ["q"],
            "additionalProperties": False,
        }

    async def call(self, arguments: dict) -> dict:
        return await wiki_get("search/", q=arguments["q"])
