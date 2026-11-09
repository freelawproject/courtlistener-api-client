"""Tests for the MCP server's FastMCP middleware."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastmcp.exceptions import ToolError
from fastmcp.server.auth.auth import AccessToken

from courtlistener.mcp.auth_types import (
    NO_CLIENT_ID,
    UNKNOWN_CLIENT_ID,
    TokenKind,
)
from courtlistener.mcp.middleware import WikiToolAccess


def access_token(scopes=("api",), kind=TokenKind.OAUTH, client_id="c"):
    return AccessToken(
        token="t",
        client_id=client_id,
        scopes=list(scopes),
        claims={"token_kind": kind},
    )


class TestWikiToolAccess:
    @staticmethod
    def as_session(monkeypatch, token):
        monkeypatch.setattr(
            "courtlistener.mcp.middleware.get_access_token", lambda: token
        )

    @pytest.mark.parametrize("excluded", [set(), {"chatgpt"}])
    def test_an_oauth_session_with_an_unknown_client_is_excluded(
        self, monkeypatch, excluded
    ):
        """Until its id is known, a session could be a blocked client
        caching its tool list, so it doesn't get the wiki tools."""
        self.as_session(monkeypatch, access_token(client_id=UNKNOWN_CLIENT_ID))
        assert WikiToolAccess(excluded).is_excluded()

    @pytest.mark.parametrize("client_id", [NO_CLIENT_ID, UNKNOWN_CLIENT_ID])
    def test_an_api_token_session_is_never_excluded(
        self, monkeypatch, client_id
    ):
        self.as_session(
            monkeypatch,
            access_token(["api"], kind=TokenKind.API, client_id=client_id),
        )
        assert not WikiToolAccess({client_id}).is_excluded()

    @pytest.fixture
    def client(self, monkeypatch):
        def use(client_id):
            token = (
                None
                if client_id is None
                else access_token(client_id=client_id)
            )
            monkeypatch.setattr(
                "courtlistener.mcp.middleware.get_access_token", lambda: token
            )

        return use

    @pytest.mark.asyncio
    async def test_hides_the_wiki_tools_from_an_excluded_client(self, client):
        client("chatgpt")
        tools = [
            SimpleNamespace(name="search"),
            SimpleNamespace(name="wiki_search"),
        ]
        listed = await WikiToolAccess({"chatgpt"}).on_list_tools(
            None, AsyncMock(return_value=tools)
        )
        assert [tool.name for tool in listed] == ["search"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("client_id", ["claude", None])
    async def test_lists_them_for_everyone_else(self, client, client_id):
        client(client_id)
        tools = [SimpleNamespace(name="wiki_search")]
        listed = await WikiToolAccess({"chatgpt"}).on_list_tools(
            None, AsyncMock(return_value=tools)
        )
        assert listed == tools

    @pytest.mark.asyncio
    async def test_refuses_an_excluded_clients_wiki_call(self, client):
        client("chatgpt")
        context = SimpleNamespace(message=SimpleNamespace(name="wiki_search"))
        call_next = AsyncMock()
        with pytest.raises(ToolError):
            await WikiToolAccess({"chatgpt"}).on_call_tool(context, call_next)
        call_next.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_lets_its_other_calls_through(self, client):
        client("chatgpt")
        context = SimpleNamespace(message=SimpleNamespace(name="search"))
        call_next = AsyncMock(return_value="ok")
        assert (
            await WikiToolAccess({"chatgpt"}).on_call_tool(context, call_next)
            == "ok"
        )
