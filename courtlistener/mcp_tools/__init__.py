from courtlistener.mcp_tools.mcp_tool import MCPTool
from courtlistener.mcp_tools.search_tool import SearchTool

mcp_tool_registry: list[type[MCPTool]] = [
    SearchTool,
]

MCP_TOOLS = {mcp_tool.name: mcp_tool() for mcp_tool in mcp_tool_registry}
