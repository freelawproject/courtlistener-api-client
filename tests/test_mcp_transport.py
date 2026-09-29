"""Tests for the MCP server's shared connection pool."""

import httpx
import pytest

from courtlistener.mcp.transport import (
    SharedTransport,
    close_pool,
    get_transport,
)


class TestSharedPool:
    def test_pool_is_created_once(self):
        assert get_transport().pool is get_transport().pool

    @pytest.mark.asyncio
    async def test_closing_a_transport_keeps_the_pool(self, mock_http):
        requests = mock_http(lambda request: httpx.Response(200))
        async with httpx.AsyncClient(transport=get_transport()) as http:
            await http.get("https://www.courtlistener.com/api/rest/v4/")
        assert not get_transport().pool.closed
        async with httpx.AsyncClient(transport=get_transport()) as http:
            await http.get("https://www.courtlistener.com/api/rest/v4/")
        assert len(requests) == 2

    @pytest.mark.asyncio
    async def test_close_pool_resets_it(self, mock_http):
        mock_http(lambda request: httpx.Response(200))
        pool = get_transport().pool
        await close_pool()
        assert pool.closed
        assert get_transport().pool is not pool

    def test_transport_wraps_the_pool(self):
        transport = get_transport()
        assert isinstance(transport, SharedTransport)
        assert isinstance(transport.pool, httpx.AsyncHTTPTransport)

    def test_server_shutdown_closes_the_pool(self, mock_http):
        from starlette.testclient import TestClient

        from courtlistener.mcp.server import create_mcp_server

        mock_http(lambda request: httpx.Response(200))
        app = create_mcp_server().http_app(path="/")
        with TestClient(app):
            pool = get_transport().pool
            assert not pool.closed
        assert pool.closed
