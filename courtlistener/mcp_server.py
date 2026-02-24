from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from courtlistener.mcp_tools import MCP_TOOLS

server = Server("courtlistener")

session: dict = {}


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [mcp_tool.get_tool() for mcp_tool in MCP_TOOLS.values()]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    mcp_tool = MCP_TOOLS.get(name)
    if mcp_tool is None:
        raise ValueError(f"Unknown tool: {name}")
    return mcp_tool(arguments, session)


def main() -> None:
    """Run the MCP server."""
    import asyncio

    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    asyncio.run(run())


if __name__ == "__main__":
    main()
