import json

import httpx
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools import ToolResult
from mcp.types import TextContent

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.tools import MCP_TOOLS
from courtlistener.mcp.tools.utils import (
    invalidate_token_cache,
    json_default,
)


class ToolHandlerMiddleware(Middleware):
    async def on_list_tools(self, context: MiddlewareContext, call_next):
        return [mcp_tool.get_tool() for mcp_tool in MCP_TOOLS.values()]

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        name = context.message.name
        arguments = context.message.arguments

        mcp_tool = MCP_TOOLS.get(name)
        if mcp_tool is None:
            raise ValueError(f"Unknown tool: {name}")

        ctx = context.fastmcp_context
        if ctx is None:
            raise ValueError("No context found")

        try:
            result = await mcp_tool(arguments, ctx)
        except CourtListenerAPIError as exc:
            if exc.status_code == 401:
                # CL rejected a token our verifier previously accepted
                # (revoked or rotated mid-cache). Drop the cache entry so
                # the next MCP request re-runs userinfo, fails verification,
                # and gets a proper HTTP 401 from the auth middleware —
                # which is what triggers the client's OAuth refresh flow.
                #
                # We can't emit the 401 for *this* request from inside the
                # tool handler (the HTTP response has already committed to
                # 200 for the JSON-RPC envelope). The tool-level error
                # below is the best we can do here; the follow-up request
                # gets the clean signal.
                try:
                    access_token = get_access_token()
                except RuntimeError:
                    access_token = None
                if access_token is not None:
                    await invalidate_token_cache(access_token.token)
                raise ToolError(
                    "CourtListener rejected the request as unauthorized. "
                    "Your session may have expired; retry to re-authenticate."
                ) from exc
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            raise ToolError(
                f"Upstream CourtListener request failed: {exc}"
            ) from exc

        if isinstance(result, dict):
            result = json.dumps(result, default=json_default, indent=2)
        if isinstance(result, str):
            return ToolResult(
                content=[TextContent(type="text", text=result)],
            )
        else:
            raise ValueError(f"Invalid result type: {type(result)}")
