from mcp.types import ToolAnnotations

from courtlistener.mcp.tools.utils import wiki_get
from courtlistener.mcp.tools.wiki_tool import (
    WIKI_PAGE_PROPERTY,
    WikiTool,
    tidy_listing,
    wiki_page_params,
)


class WikiListPagesTool(WikiTool):
    """List the Free Law Project wiki pages you can read.

    Returns each page's `path` (pass it to `wiki_read_page`), title,
    description, `updated_at` and `url`, ordered by directory, then
    title. Public pages are always listed; pages for FLP staff and pages
    shared with you appear when your CourtListener account's email has
    access to them on the wiki. Pages come 50 at a time; the response
    gives the `total` and, when there are more, the `next_page` to pass
    as `page`. To find pages on a topic, `wiki_search` is usually better.
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
            "properties": {"page": WIKI_PAGE_PROPERTY},
            "additionalProperties": False,
        }

    async def call_wiki(self, arguments: dict) -> dict:
        data = await wiki_get("pages/", **wiki_page_params(arguments))
        return tidy_listing(data, "pages", arguments)
