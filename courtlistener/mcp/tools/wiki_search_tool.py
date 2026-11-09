from fastmcp.server.dependencies import get_access_token
from mcp.types import ToolAnnotations

from courtlistener.mcp.auth_types import TokenKind
from courtlistener.mcp.settings import WIKI_BASE_URL, WIKI_SCOPES
from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.utils import wiki_get

MISSING_WIKI_SCOPES_MESSAGE = (
    "This connection can't search the Free Law Project wiki yet. The wiki "
    "needs three permissions your CourtListener sign-in hasn't granted: "
    "`wiki`, `profile` and `email`. To get them, disconnect this "
    "CourtListener connector and connect it again, then approve the "
    "permissions CourtListener asks for. In some apps that isn't enough, "
    "and you'll need to fully uninstall the connector and reinstall it."
)


def missing_wiki_scopes() -> bool:
    """Whether the request's OAuth sign-in lacks a scope the wiki needs.

    API token and stdio sessions have no scopes; they read the wiki as
    the public, as ``wiki_get`` sends them without a credential."""
    token = get_access_token()
    if token is None or token.claims.get("token_kind") == TokenKind.API:
        return False
    return not set(WIKI_SCOPES) <= set(token.scopes)


class WikiSearchTool(MCPTool):
    """Search the Free Law Project wiki pages you can read.

    Full-text search over page titles and content. The query supports
    quoted phrases, `-word` to exclude a word, `title:word`, and
    `in:<directory path>` to search one directory. Each result carries
    the page's title, description, a snippet of the matching text and a
    `url` to open it. Results come 20 to a page, best first; the response
    gives the `total` and, when there are more, the `next_page` to pass
    as `page`.
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
                "page": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Page of results to return (default 1).",
                },
            },
            "required": ["q"],
            "additionalProperties": False,
        }

    async def call(self, arguments: dict) -> dict | str:
        if missing_wiki_scopes():
            return MISSING_WIKI_SCOPES_MESSAGE
        params = {"q": arguments["q"]}
        if arguments.get("page") is not None:
            params["page"] = arguments["page"]
        data = await wiki_get("search/", **params)
        for result in data.get("results", []):
            if "path" in result:
                result["url"] = f"{WIKI_BASE_URL}/c/{result['path']}"
        return data
