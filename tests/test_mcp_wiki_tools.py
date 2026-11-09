"""Tests for the wiki tools."""

import sys
from unittest.mock import AsyncMock

import pytest
from fastmcp.server.auth.auth import AccessToken

from courtlistener.mcp.auth_types import TokenKind
from courtlistener.mcp.exceptions import (
    ToolArgumentValidationError,
    WikiAPIError,
)
from courtlistener.mcp.middleware import WIKI_TOOL_NAMES
from courtlistener.mcp.settings import WIKI_BASE_URL
from courtlistener.mcp.tools import MCP_TOOLS, wiki_tool
from courtlistener.mcp.tools.wiki_list_pages_tool import WikiListPagesTool
from courtlistener.mcp.tools.wiki_read_page_tool import WikiReadPageTool
from courtlistener.mcp.tools.wiki_search_tool import WikiSearchTool
from courtlistener.mcp.tools.wiki_tool import MISSING_WIKI_SCOPES_MESSAGE

FULL_SCOPES = ["openid", "api", "wiki", "profile", "email"]
SUMMARY = {"path": "eng/deploys", "title": "Deploys", "description": "…"}
PAGE_URL = f"{WIKI_BASE_URL}/c/eng/deploys"

# (tool, arguments, the wiki_get call it makes, what the wiki answers)
CALLS = [
    (
        WikiListPagesTool(),
        {},
        (("pages/",), {}),
        {"total": 1, "page": 1, "next_page": None, "pages": [dict(SUMMARY)]},
    ),
    (
        WikiSearchTool(),
        {"q": "deploy"},
        (("search/",), {"q": "deploy"}),
        {"total": 1, "page": 1, "next_page": None, "results": [dict(SUMMARY)]},
    ),
    (
        WikiReadPageTool(),
        {"path": "eng/deploys"},
        (("pages/eng/deploys",), {}),
        {**SUMMARY, "content": "# Deploys"},
    ),
]


def access_token(scopes=FULL_SCOPES, kind=TokenKind.OAUTH):
    return AccessToken(
        token="t", client_id="c", scopes=scopes, claims={"token_kind": kind}
    )


@pytest.fixture
def sign_in(monkeypatch):
    def use(token):
        monkeypatch.setattr(wiki_tool, "get_access_token", lambda: token)

    use(access_token())
    return use


def patch_wiki_get(monkeypatch, tool, answer):
    mock = AsyncMock(return_value=answer)
    monkeypatch.setattr(sys.modules[type(tool).__module__], "wiki_get", mock)
    return mock


def test_the_middleware_guards_every_wiki_tool():
    assert {
        "wiki_list_pages",
        "wiki_search",
        "wiki_read_page",
    } == WIKI_TOOL_NAMES
    assert set(MCP_TOOLS) >= WIKI_TOOL_NAMES


@pytest.mark.asyncio
@pytest.mark.parametrize("tool, arguments, call, answer", CALLS)
async def test_each_tool_asks_the_wiki_for_the_right_thing(
    monkeypatch, sign_in, tool, arguments, call, answer
):
    wiki_get = patch_wiki_get(monkeypatch, tool, answer)
    await tool.call(arguments)
    wiki_get.assert_awaited_once_with(*call[0], **call[1])


@pytest.mark.asyncio
@pytest.mark.parametrize("tool, arguments, call, answer", CALLS)
async def test_each_page_comes_back_with_its_url(
    monkeypatch, sign_in, tool, arguments, call, answer
):
    patch_wiki_get(monkeypatch, tool, answer)
    result = await tool.call(arguments)
    pages = result.get("pages") or result.get("results") or [result]
    assert [page["url"] for page in pages] == [PAGE_URL]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool, arguments, call",
    [
        (WikiListPagesTool(), {"page": 2}, (("pages/",), {"page": 2})),
        (
            WikiSearchTool(),
            {"q": "deploy", "page": 3},
            (("search/",), {"q": "deploy", "page": 3}),
        ),
    ],
)
async def test_the_listing_tools_pass_the_page_through(
    monkeypatch, sign_in, tool, arguments, call
):
    wiki_get = patch_wiki_get(monkeypatch, tool, {})
    await tool.call(arguments)
    wiki_get.assert_awaited_once_with(*call[0], **call[1])


@pytest.mark.parametrize(
    "tool", [WikiListPagesTool(), WikiSearchTool()], ids=lambda t: t.name
)
def test_the_listing_tools_take_a_positive_page(tool):
    assert tool.parameters["properties"]["page"]["minimum"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value, requested",
    [
        ("eng/deploys", "pages/eng/deploys"),
        ("/eng/deploys/", "pages/eng/deploys"),
        (f"{WIKI_BASE_URL}/c/eng/deploys", "pages/eng/deploys"),
        (f"{WIKI_BASE_URL}/c/eng/deploys/?x=1#top", "pages/eng/deploys"),
        # Links as they appear in page content.
        ("/c/eng/deploys/", "pages/eng/deploys"),
        ("/c/eng/deploys#pacer-fetch", "pages/eng/deploys"),
        ("eng/deploys#pacer-fetch", "pages/eng/deploys"),
        # The wiki's own link syntax for pages.
        ("#eng/deploys", "pages/eng/deploys"),
        ("#eng/deploys#pacer-fetch", "pages/eng/deploys"),
        # A bare path under a directory named `c` is left alone.
        ("c/eng", "pages/c/eng"),
        ("eng/a page", "pages/eng/a%20page"),
    ],
)
async def test_read_page_accepts_a_path_or_a_page_url(
    monkeypatch, sign_in, value, requested
):
    tool = WikiReadPageTool()
    wiki_get = patch_wiki_get(monkeypatch, tool, dict(SUMMARY))
    await tool.call({"path": value})
    wiki_get.assert_awaited_once_with(requested)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value",
    [
        "",
        "/",
        "/c/",
        "#",
        "https://example.com/c/eng",
        f"{WIKI_BASE_URL}/eng",
    ],
)
async def test_read_page_rejects_what_is_not_a_page(
    monkeypatch, sign_in, value
):
    tool = WikiReadPageTool()
    wiki_get = patch_wiki_get(monkeypatch, tool, {})
    with pytest.raises(ToolArgumentValidationError) as exc:
        await tool.call({"path": value})
    assert exc.value.argument_names == ["path"]
    wiki_get.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("tool, arguments, call, answer", CALLS)
@pytest.mark.parametrize(
    "scopes",
    [
        ["openid", "api"],
        ["openid", "api", "wiki"],
        ["openid", "api", "wiki", "email"],
    ],
)
async def test_a_sign_in_without_the_wiki_scopes_is_told_to_reconnect(
    monkeypatch, sign_in, tool, arguments, call, answer, scopes
):
    sign_in(access_token(scopes))
    wiki_get = patch_wiki_get(monkeypatch, tool, answer)
    assert await tool.call(arguments) == MISSING_WIKI_SCOPES_MESSAGE
    wiki_get.assert_not_awaited()


def test_the_reconnect_message_names_the_scopes_and_the_fixes():
    for word in ("`wiki`", "`profile`", "`email`", "disconnect", "uninstall"):
        assert word in MISSING_WIKI_SCOPES_MESSAGE


@pytest.mark.asyncio
@pytest.mark.parametrize("tool, arguments, call, answer", CALLS)
@pytest.mark.parametrize(
    "token", [None, access_token(["api"], kind=TokenKind.API)]
)
async def test_api_token_and_stdio_sessions_read_as_the_public(
    monkeypatch, sign_in, tool, arguments, call, answer, token
):
    """They have no OAuth scopes to grant; ``wiki_get`` sends them to the
    wiki without a credential, so they see public pages."""
    sign_in(token)
    wiki_get = patch_wiki_get(monkeypatch, tool, answer)
    await tool.call(arguments)
    wiki_get.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_missing_page_points_at_searching_the_directory(
    monkeypatch, sign_in
):
    tool = WikiReadPageTool()
    patch_wiki_get(monkeypatch, tool, None).side_effect = WikiAPIError(
        "The wiki has no page you can read at 'eng/help'.", "404"
    )
    with pytest.raises(WikiAPIError) as exc:
        await tool.call({"path": "eng/help"})
    assert "`in:eng/help`" in str(exc.value)
    assert exc.value.status == "404"


@pytest.mark.asyncio
async def test_other_wiki_errors_pass_through(monkeypatch, sign_in):
    tool = WikiReadPageTool()
    error = WikiAPIError("The wiki returned HTTP 500.", "500")
    patch_wiki_get(monkeypatch, tool, None).side_effect = error
    with pytest.raises(WikiAPIError) as exc:
        await tool.call({"path": "eng/help"})
    assert exc.value is error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool, arguments, key",
    [
        (WikiListPagesTool(), {"page": 8}, "pages"),
        (WikiSearchTool(), {"q": "api", "page": 99}, "results"),
    ],
)
async def test_a_page_past_the_end_comes_back_empty(
    monkeypatch, sign_in, tool, arguments, key
):
    """The wiki answers it with the last page, which a caller looping on
    ``page`` would see twice."""
    last = {"total": 95, "page": 5, "next_page": None, key: [dict(SUMMARY)]}
    patch_wiki_get(monkeypatch, tool, last)
    result = await tool.call(arguments)
    assert result == {
        "total": 95,
        "page": arguments["page"],
        "next_page": None,
        key: [],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("tool, arguments, call, answer", CALLS)
async def test_text_comes_back_with_plain_newlines(
    monkeypatch, sign_in, tool, arguments, call, answer
):
    crlf = {"description": "a\r\nb", "snippet": "c\r\nd", "content": "e\r\nf"}
    answer = {
        key: [{**item, **crlf} for item in value]
        if isinstance(value, list)
        else value
        for key, value in answer.items()
    }
    if "content" in answer:
        answer.update(crlf)
    patch_wiki_get(monkeypatch, tool, answer)
    result = await tool.call(arguments)
    pages = result.get("pages") or result.get("results") or [result]
    for page in pages:
        assert "\r" not in page["description"] + page["snippet"]
        assert page["content"].count("\n") == 1
