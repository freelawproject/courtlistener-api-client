from courtlistener.mcp.tools.call_endpoint_tool import CallEndpointTool
from courtlistener.mcp.tools.get_choices_tool import GetChoicesTool
from courtlistener.mcp.tools.get_counts_tool import GetCountsTool
from courtlistener.mcp.tools.get_endpoint_item_tool import GetEndpointItemTool
from courtlistener.mcp.tools.get_endpoint_schema_tool import (
    GetEndpointSchemaTool,
)
from courtlistener.mcp.tools.get_more_results_tool import GetMoreResultsTool
from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.search_tool import SearchTool

mcp_tool_registry: list[type[MCPTool]] = [
    SearchTool,
    GetEndpointSchemaTool,
    CallEndpointTool,
    GetEndpointItemTool,
    GetChoicesTool,
    GetCountsTool,
    GetMoreResultsTool,
]

MCP_TOOLS = {mcp_tool.name: mcp_tool() for mcp_tool in mcp_tool_registry}
