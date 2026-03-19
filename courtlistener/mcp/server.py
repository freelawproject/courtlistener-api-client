from __future__ import annotations

import argparse
import os

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool

from courtlistener.mcp.tools import MCP_TOOLS

server = Server("courtlistener")

# Per-session state for stdio transport (single user).
# For HTTP transport, sessions are managed per-connection.
_stdio_session: dict = {}


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [mcp_tool.get_tool() for mcp_tool in MCP_TOOLS.values()]


@server.call_tool()
async def call_tool(
    name: str, arguments: dict
) -> list[TextContent] | CallToolResult:
    """Handle tool calls."""
    mcp_tool = MCP_TOOLS.get(name)
    if mcp_tool is None:
        raise ValueError(f"Unknown tool: {name}")
    return mcp_tool(arguments, _stdio_session)


def run_stdio() -> None:
    """Run the MCP server with stdio transport (local)."""
    import asyncio

    async def _run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    asyncio.run(_run())


def run_http(host: str, port: int) -> None:
    """Run the MCP server with Streamable HTTP transport (remote)."""
    import uvicorn
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.cors import CORSMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Mount, Route

    from courtlistener.mcp.auth import AuthMiddleware

    mcp_app = server.streamable_http_app()

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    app = Starlette(
        routes=[
            Route("/health", health),
            Mount("/mcp", app=mcp_app),
        ],
        middleware=[
            # AuthMiddleware must come first so the token context var
            # is set before tool handlers run.
            Middleware(AuthMiddleware),
            Middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["GET", "POST", "DELETE"],
                expose_headers=["Mcp-Session-Id"],
            ),
        ],
    )

    uvicorn.run(app, host=host, port=port)


def main() -> None:
    """Run the MCP server."""
    parser = argparse.ArgumentParser(
        description="CourtListener MCP Server"
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default=os.environ.get("MCP_TRANSPORT", "stdio"),
        help=(
            "Transport to use. 'stdio' for local MCP clients, "
            "'streamable-http' for remote. "
            "Can also be set via MCP_TRANSPORT env var. "
            "(default: stdio)"
        ),
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("MCP_HOST", "0.0.0.0"),
        help="Host to bind to (HTTP only). (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MCP_PORT", "8000")),
        help="Port to listen on (HTTP only). (default: 8000)",
    )
    args = parser.parse_args()

    if args.transport == "stdio":
        run_stdio()
    else:
        run_http(args.host, args.port)


if __name__ == "__main__":
    main()
