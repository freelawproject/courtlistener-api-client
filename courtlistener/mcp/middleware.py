import json
from datetime import date

from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools import ToolResult
from mcp.types import TextContent

from courtlistener.mcp.tools import MCP_TOOLS


def json_default(obj):
    if isinstance(obj, date):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


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
        result = await mcp_tool(arguments, ctx)
        if isinstance(result, dict):
            result = json.dumps(result, default=json_default, indent=2)
        if isinstance(result, str):
            return ToolResult(
                content=[TextContent(type="text", text=result)],
            )
        else:
            raise ValueError(f"Invalid result type: {type(result)}")
