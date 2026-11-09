from urllib.parse import quote, urlsplit

from mcp.types import ToolAnnotations

from courtlistener.mcp.exceptions import (
    ToolArgumentValidationError,
    WikiAPIError,
)
from courtlistener.mcp.settings import WIKI_BASE_URL
from courtlistener.mcp.tools.utils import wiki_get
from courtlistener.mcp.tools.wiki_tool import WikiTool, tidy_page


class WikiReadPageTool(WikiTool):
    """Read one Free Law Project wiki page as Markdown.

    `path` is the page's `path` from `wiki_list_pages` or `wiki_search`,
    e.g. `engineering/deploys`. The page's `url` works too, as do links
    found in page content: the wiki's own `#engineering/deploys` links
    and `/c/engineering/deploys/` ones. An `#anchor` on any of them is
    ignored. Returns the page's path, title, description, `updated_at`,
    `url` and its `content` as Markdown. Directories aren't pages: to see
    a directory's pages, search it with `in:<directory path>`.
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
                    "description": (
                        "The page's path, e.g. `engineering/deploys`, its "
                        "wiki URL, or a link from page content (`#...` or "
                        "`/c/...`)."
                    ),
                }
            },
            "required": ["path"],
            "additionalProperties": False,
        }

    def page_path(self, value: str) -> str:
        """The wiki content path *value* names: a path, a page URL, or a
        link from page content (the wiki's ``#path`` syntax, or a site
        link ``/c/...``), less any query or ``#anchor``. A bare ``c/...``
        is a path, under a directory ``c``."""
        value = value.strip().removeprefix("#")
        url = urlsplit(value)
        is_url = bool(url.scheme or url.netloc)
        if is_url and (
            url.netloc != urlsplit(WIKI_BASE_URL).netloc
            or not url.path.startswith("/c/")
        ):
            raise self.invalid_path(f"{value!r} is not a wiki page URL.")
        path = url.path
        if path.startswith("/c/"):
            path = path.removeprefix("/c/")
        path = path.strip("/")
        if not path:
            raise self.invalid_path("`path` must name a wiki page.")
        return path

    def invalid_path(self, message: str) -> ToolArgumentValidationError:
        return ToolArgumentValidationError(
            f"Invalid arguments for tool '{self.name}':\n- {message}",
            tool_name=self.name,
            argument_names=["path"],
        )

    async def call_wiki(self, arguments: dict) -> dict:
        path = self.page_path(arguments["path"])
        try:
            page = await wiki_get(f"pages/{quote(path, safe='/')}")
        except WikiAPIError as exc:
            if exc.status != "404":
                raise
            raise WikiAPIError(
                f"The wiki has no page you can read at {path!r}. If that's "
                "a directory, search its pages with `wiki_search` and "
                f"`in:{path}`.",
                exc.status,
            ) from exc
        return tidy_page(page)
