from fastmcp.server.dependencies import get_access_token

from courtlistener.mcp.auth_types import TokenKind
from courtlistener.mcp.settings import WIKI_BASE_URL, WIKI_SCOPES
from courtlistener.mcp.tools.mcp_tool import MCPTool

MISSING_WIKI_SCOPES_MESSAGE = (
    "This connection can't read the Free Law Project wiki yet. The wiki "
    "needs three permissions your CourtListener sign-in hasn't granted: "
    "`wiki`, `profile` and `email`. To get them, disconnect this "
    "CourtListener connector and connect it again, then approve the "
    "permissions CourtListener asks for. In some apps that isn't enough, "
    "and you'll need to fully uninstall the connector and reinstall it."
)

# The `page` argument of the wiki's paginated list and search endpoints.
WIKI_PAGE_PROPERTY = {
    "type": "integer",
    "minimum": 1,
    "description": "Page of results to return (default 1).",
}


def missing_wiki_scopes() -> bool:
    """Whether the request's OAuth sign-in lacks a scope the wiki needs.

    API token and stdio sessions have no scopes; they read the wiki as
    the public, as ``wiki_get`` sends them without a credential."""
    token = get_access_token()
    if token is None or token.claims.get("token_kind") == TokenKind.API:
        return False
    return not set(WIKI_SCOPES) <= set(token.scopes)


def wiki_page_url(path: str) -> str:
    """The URL of the wiki page at *path*."""
    return f"{WIKI_BASE_URL}/c/{path}"


def tidy_page(page: dict) -> dict:
    """*page* with a ``url`` and its text fields' CRLFs turned into LFs,
    which the wiki stores but which only cost the model tokens."""
    for field in ("description", "snippet", "content"):
        if isinstance(page.get(field), str):
            page[field] = page[field].replace("\r\n", "\n")
    if "path" in page:
        page["url"] = wiki_page_url(page["path"])
    return page


def tidy_listing(data: dict, key: str, arguments: dict) -> dict:
    """A page of the wiki's list or search results, made ready to return.

    Each page summary under *key* is tidied. The wiki answers a ``page``
    past the end with the last page; that comes back empty instead, under
    the page number asked for, so a caller looping on ``page`` sees no
    duplicates."""
    requested = arguments.get("page")
    if requested is not None and data.get("page") not in (None, requested):
        data.update(page=requested, next_page=None, **{key: []})
    for page in data.get(key, []):
        tidy_page(page)
    return data


def wiki_page_params(arguments: dict) -> dict:
    """The ``page`` query parameter, when the caller asked for one."""
    page = arguments.get("page")
    return {} if page is None else {"page": page}


class WikiTool(MCPTool):
    """A tool that reads the Free Law Project wiki as the current user.

    A sign-in without ``WIKI_SCOPES`` gets a message asking the user to
    reconnect, and the wiki is not called."""

    async def call(self, arguments: dict) -> dict | str:
        if missing_wiki_scopes():
            return MISSING_WIKI_SCOPES_MESSAGE
        return await self.call_wiki(arguments)

    async def call_wiki(self, arguments: dict) -> dict:
        raise NotImplementedError("call_wiki must be implemented by subclass")
