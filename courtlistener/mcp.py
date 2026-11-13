"""The CourtListener MCP server has moved to its own repository.

This stub keeps ``courtlistener.mcp`` so that anything still importing it
gets a pointer to the new home instead of a bare ``ModuleNotFoundError``.
"""

MESSAGE = (
    "The CourtListener MCP server is no longer part of "
    "courtlistener-api-client. It now lives at "
    "https://github.com/freelawproject/courtlistener-mcp. To connect to the "
    "hosted server, see https://wiki.free.law/c/courtlistener/help/api/mcp."
)

raise ImportError(MESSAGE)
