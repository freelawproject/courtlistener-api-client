from collections.abc import Collection, Sequence
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

from courtlistener.mcp.auth_types import UNKNOWN_CLIENT_ID, TokenKind

WIKI_TOOL_NAMES = frozenset({"wiki_search"})


class WikiToolAccess(Middleware):
    """Hide the wiki tools from, and refuse their calls for, the OAuth
    clients in *excluded*, and OAuth sessions whose client is unknown (so a
    blocked client can't cache a tool list before its id is known). API
    token and stdio sessions are never excluded.
    """

    def __init__(self, excluded: Collection[str]) -> None:
        self.excluded = frozenset(excluded)

    def is_excluded(self) -> bool:
        """Whether the current request's client may not use the wiki tools."""
        token = get_access_token()
        if token is None or token.claims.get("token_kind") == TokenKind.API:
            return False
        return (
            token.client_id == UNKNOWN_CLIENT_ID
            or token.client_id in self.excluded
        )

    async def on_list_tools(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Sequence[Any]],
    ) -> Sequence[Any]:
        tools = await call_next(context)
        if not self.is_excluded():
            return tools
        return [tool for tool in tools if tool.name not in WIKI_TOOL_NAMES]

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        if context.message.name in WIKI_TOOL_NAMES and self.is_excluded():
            raise ToolError("The wiki tools are not available to this client.")
        return await call_next(context)
