import json

import httpx
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools import ToolResult
from mcp.types import TextContent

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.exceptions import (
    SentryExemptToolError,
    UnauthorizedToolError,
    UpstreamCourtListenerError,
)
from courtlistener.mcp.session import get_session, json_default
from courtlistener.mcp.tools import MCP_TOOLS


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

        mcp_tool.validate_arguments(arguments)

        try:
            result = await mcp_tool(arguments, ctx)
        except CourtListenerAPIError as exc:
            if exc.status_code == 401:
                # Bust the cache if token rejected by CL
                try:
                    access_token = get_access_token()
                except RuntimeError:
                    access_token = None
                if access_token is not None:
                    await get_session().invalidate_token(access_token.token)
                message = (
                    "CourtListener rejected the request as unauthorized. "
                    "Your session may have expired; retry to re-authenticate."
                )
                if access_token is not None and access_token.claims.get(
                    "cached"
                ):
                    # If it was cached, this is expected. Make exempt.
                    raise SentryExemptToolError(message) from exc
                # Otherwise, this is a real disagreement between CL and MCP.
                raise UnauthorizedToolError(message, tool_name=name) from exc
            elif exc.status_code == 429:
                # Routine API rate limit errors are exempt.
                raise SentryExemptToolError(
                    f"Rate limit exceeded: {exc}. For higher rate limits, "
                    "you can upgrade your membership at https://donate.free.law/forms/membership"
                ) from exc
            elif exc.status_code >= 500:
                raise UpstreamCourtListenerError(
                    f"CourtListener API error: {exc}",
                    tool_name=name,
                    status=str(exc.status_code),
                ) from exc
            else:
                raise ToolError(f"CourtListener API error: {exc}") from exc
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            raise UpstreamCourtListenerError(
                f"Upstream CourtListener request failed: {exc}",
                tool_name=name,
                status="connection",
            ) from exc

        if isinstance(result, dict):
            result = json.dumps(result, default=json_default, indent=2)
        if isinstance(result, str):
            return ToolResult(
                content=[TextContent(type="text", text=result)],
            )
        else:
            raise ValueError(f"Invalid result type: {type(result)}")
