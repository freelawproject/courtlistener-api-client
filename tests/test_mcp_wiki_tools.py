"""Tests for the wiki tools."""

import sys

import pytest

from courtlistener.mcp.tools.wiki_list_pages_tool import WikiListPagesTool
from courtlistener.mcp.tools.wiki_read_page_tool import WikiReadPageTool
from courtlistener.mcp.tools.wiki_search_tool import WikiSearchTool


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool, arguments, path, params",
    [
        (WikiListPagesTool(), {}, "pages/", {}),
        (WikiSearchTool(), {"q": "deploy"}, "search/", {"q": "deploy"}),
        (
            WikiReadPageTool(),
            {"path": "/eng/deploys/"},
            "pages/eng/deploys",
            {},
        ),
    ],
)
async def test_each_tool_asks_the_wiki_for_the_right_thing(
    monkeypatch, tool, arguments, path, params
):
    seen = {}

    async def wiki_get(p, **kw):
        seen.update(path=p, params=kw)
        return {"ok": True}

    monkeypatch.setattr(
        sys.modules[type(tool).__module__], "wiki_get", wiki_get
    )
    assert await tool.call(arguments) == {"ok": True}
    assert seen == {"path": path, "params": params}
