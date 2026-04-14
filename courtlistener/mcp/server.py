from fastmcp import FastMCP

from courtlistener.mcp.middleware import ToolHandlerMiddleware

mcp = FastMCP("courtlistener")

mcp.add_middleware(ToolHandlerMiddleware())


if __name__ == "__main__":
    mcp.run(transport="http", port=8000)
