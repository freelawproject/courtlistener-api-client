from mcp.types import ToolAnnotations

from courtlistener.mcp.tools.utils import wiki_get
from courtlistener.mcp.tools.wiki_tool import (
    WIKI_PAGE_PROPERTY,
    WikiTool,
    tidy_listing,
    wiki_page_params,
)


class WikiSearchTool(WikiTool):
    """Search the Free Law Project wiki pages you can read.

    Full-text search over page titles and content. The query supports
    quoted phrases, `-word` to exclude a word, `title:word`, and
    `in:<directory path>` to search one directory. Each result carries
    the page's `path` (pass it to `wiki_read_page`), title, description,
    `updated_at`, a `snippet` of the matching text and a `url` to open
    it. Results come 20 to a page, best first; the response gives the
    `total` and, when there are more, the `next_page` to pass as `page`.
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
                "q": {"type": "string", "description": "The search query."},
                "page": WIKI_PAGE_PROPERTY,
            },
            "required": ["q"],
            "additionalProperties": False,
        }

    async def call_wiki(self, arguments: dict) -> dict:
        data = await wiki_get(
            "search/", q=arguments["q"], **wiki_page_params(arguments)
        )
        return tidy_listing(data, "results", arguments)
