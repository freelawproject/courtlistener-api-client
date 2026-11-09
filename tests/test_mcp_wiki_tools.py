"""Tests for the wiki search tool."""

from unittest.mock import AsyncMock

import pytest
from fastmcp.server.auth.auth import AccessToken

from courtlistener.mcp.auth_types import (
    TokenKind,
)
from courtlistener.mcp.settings import WIKI_BASE_URL
from courtlistener.mcp.tools import wiki_search_tool
from courtlistener.mcp.tools.wiki_search_tool import (
    MISSING_WIKI_SCOPES_MESSAGE,
    WikiSearchTool,
)

FULL_SCOPES = ["openid", "api", "wiki", "profile", "email"]
RESULTS = {
    "total": 1,
    "page": 1,
    "next_page": None,
    "results": [{"path": "eng/deploys", "title": "Deploys", "snippet": "…"}],
}


def access_token(scopes=FULL_SCOPES, kind=TokenKind.OAUTH, client_id="c"):
    return AccessToken(
        token="t",
        client_id=client_id,
        scopes=scopes,
        claims={"token_kind": kind},
    )


@pytest.fixture
def wiki_get(monkeypatch):
    mock = AsyncMock(return_value=RESULTS)
    monkeypatch.setattr(wiki_search_tool, "wiki_get", mock)
    return mock


def sign_in(monkeypatch, token):
    monkeypatch.setattr(wiki_search_tool, "get_access_token", lambda: token)


@pytest.mark.asyncio
async def test_searches_the_wiki_and_links_each_result(monkeypatch, wiki_get):
    sign_in(monkeypatch, access_token())
    result = await WikiSearchTool().call({"q": "deploy"})
    wiki_get.assert_awaited_once_with("search/", q="deploy")
    assert result["results"][0]["url"] == f"{WIKI_BASE_URL}/c/eng/deploys"


@pytest.mark.asyncio
async def test_asks_the_wiki_for_the_requested_page(monkeypatch, wiki_get):
    sign_in(monkeypatch, access_token())
    await WikiSearchTool().call({"q": "deploy", "page": 3})
    wiki_get.assert_awaited_once_with("search/", q="deploy", page=3)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scopes",
    [
        ["openid", "api"],
        ["openid", "api", "wiki"],
        ["openid", "api", "wiki", "email"],
    ],
)
async def test_a_sign_in_without_the_wiki_scopes_is_told_to_reconnect(
    monkeypatch, wiki_get, scopes
):
    sign_in(monkeypatch, access_token(scopes))
    assert await WikiSearchTool().call({"q": "deploy"}) == (
        MISSING_WIKI_SCOPES_MESSAGE
    )
    wiki_get.assert_not_awaited()


def test_the_reconnect_message_names_the_scopes_and_the_fixes():
    for word in ("`wiki`", "`profile`", "`email`", "disconnect", "uninstall"):
        assert word in MISSING_WIKI_SCOPES_MESSAGE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "token", [None, access_token(["api"], kind=TokenKind.API)]
)
async def test_api_token_and_stdio_sessions_search_as_the_public(
    monkeypatch, wiki_get, token
):
    """They have no OAuth scopes to grant; ``wiki_get`` sends them to the
    wiki without a credential, so they see public pages."""
    sign_in(monkeypatch, token)
    await WikiSearchTool().call({"q": "deploy"})
    wiki_get.assert_awaited_once()
