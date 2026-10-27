"""Tests for the wiki API helper."""

import httpx
import pytest
from fastmcp.exceptions import ToolError
from fastmcp.server.auth.auth import AccessToken

from courtlistener.mcp.auth_types import TokenKind
from courtlistener.mcp.tools import utils
from courtlistener.mcp.tools.utils import wiki_get

pytestmark = pytest.mark.asyncio


def serve(monkeypatch, handler, token=None):
    """Answer the helper's HTTP with *handler*, as a caller holding *token*."""
    real = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )
    monkeypatch.setattr(utils, "get_access_token", lambda: token)


def access_token(kind):
    return AccessToken(
        token="cl-token",
        client_id="c",
        scopes=["api"],
        claims={"token_kind": kind},
    )


async def test_forwards_the_courtlistener_token(monkeypatch):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"pages": []})

    serve(monkeypatch, handler, access_token(TokenKind.OAUTH))
    assert await wiki_get("pages/") == {"pages": []}
    assert seen["url"] == f"{utils.WIKI_BASE_URL}/api/v1/pages/"
    assert seen["auth"] == "Bearer cl-token"


@pytest.mark.parametrize("token", [None, access_token(TokenKind.API)])
async def test_reads_as_the_public_without_an_oauth_token(monkeypatch, token):
    def handler(request):
        assert "Authorization" not in request.headers
        return httpx.Response(200, json={"pages": []})

    serve(monkeypatch, handler, token)
    await wiki_get("pages/")


async def test_passes_query_parameters(monkeypatch):
    def handler(request):
        assert request.url.params["q"] == "deploy"
        return httpx.Response(200, json={"total": 0, "results": []})

    serve(monkeypatch, handler)
    assert (await wiki_get("search/", q="deploy"))["total"] == 0


async def test_names_a_missing_page(monkeypatch):
    serve(monkeypatch, lambda request: httpx.Response(404))
    with pytest.raises(ToolError, match="'eng/nope'"):
        await wiki_get("pages/eng/nope")


async def test_rejected_token_says_to_reconnect(monkeypatch):
    serve(
        monkeypatch,
        lambda request: httpx.Response(401),
        access_token(TokenKind.OAUTH),
    )
    with pytest.raises(ToolError, match="reconnect"):
        await wiki_get("pages/")


async def test_other_errors_report_the_status(monkeypatch):
    serve(monkeypatch, lambda request: httpx.Response(503))
    with pytest.raises(ToolError, match="HTTP 503"):
        await wiki_get("pages/")
