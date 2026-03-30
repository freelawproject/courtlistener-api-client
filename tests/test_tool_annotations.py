"""Tests for MCP tool annotations (readOnlyHint, destructiveHint, etc.)."""

from __future__ import annotations

from courtlistener.mcp.tools import MCP_TOOLS

READ_ONLY_TOOLS = {
    "search",
    "get_endpoint_schema",
    "call_endpoint",
    "get_endpoint_item",
    "get_choices",
    "get_counts",
    "get_more_results",
    "extract_citations",
    "analyze_citations",
    "resume_citation_analysis",
}

WRITE_TOOLS = {
    "create_search_alert",
    "delete_search_alert",
    "subscribe_to_docket_alert",
    "unsubscribe_from_docket_alert",
}

DESTRUCTIVE_TOOLS = {
    "delete_search_alert",
    "unsubscribe_from_docket_alert",
}

# Tools that operate on local data only (Pydantic schemas / eyecite);
# no network calls are made, so openWorldHint=False.
# Note: get_counts may make a lazy API call, so it is open-world.
LOCAL_ONLY_TOOLS = {
    "get_endpoint_schema",
    "get_choices",
    "extract_citations",
}


class TestToolAnnotations:
    def test_all_tools_have_annotations(self):
        """Every tool must expose a non-None annotations object."""
        for name, tool in MCP_TOOLS.items():
            t = tool.get_tool()
            assert t.annotations is not None, (
                f"{name} missing annotations"
            )

    def test_all_tools_accounted_for(self):
        """READ_ONLY_TOOLS | WRITE_TOOLS must exactly match MCP_TOOLS."""
        assert set(MCP_TOOLS.keys()) == READ_ONLY_TOOLS | WRITE_TOOLS

    def test_read_only_tools(self):
        """All read-only tools must have readOnlyHint=True."""
        for name in READ_ONLY_TOOLS:
            t = MCP_TOOLS[name].get_tool()
            assert t.annotations.readOnlyHint is True, name

    def test_write_tools(self):
        """All write tools must have readOnlyHint=False."""
        for name in WRITE_TOOLS:
            t = MCP_TOOLS[name].get_tool()
            assert t.annotations.readOnlyHint is False, name

    def test_destructive_tools(self):
        """Delete tools must have destructiveHint=True."""
        for name in DESTRUCTIVE_TOOLS:
            t = MCP_TOOLS[name].get_tool()
            assert t.annotations.destructiveHint is True, name

    def test_non_destructive_write_tools(self):
        """Create tools must have destructiveHint=False."""
        for name in WRITE_TOOLS - DESTRUCTIVE_TOOLS:
            t = MCP_TOOLS[name].get_tool()
            assert t.annotations.destructiveHint is False, name

    def test_local_tools_closed_world(self):
        """Purely-local tools must have openWorldHint=False."""
        for name in LOCAL_ONLY_TOOLS:
            t = MCP_TOOLS[name].get_tool()
            assert t.annotations.openWorldHint is False, name

    def test_api_tools_open_world(self):
        """All non-local tools must have openWorldHint=True."""
        api_tools = set(MCP_TOOLS.keys()) - LOCAL_ONLY_TOOLS
        for name in api_tools:
            t = MCP_TOOLS[name].get_tool()
            assert t.annotations.openWorldHint is True, name
