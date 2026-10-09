"""Tool registration and dispatch through FastMCP.

The tools are registered natively, so FastMCP's own ``tools/list`` and
``tools/call`` handlers serve them and ``MCPTool.run`` owns argument
validation, error translation, and serialization. These tests drive
the server through a real client session.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

import courtlistener.mcp.server as server_mod
import courtlistener.mcp.storage as storage_mod
from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.server import create_mcp_server
from courtlistener.mcp.session import (
    InMemorySession,
    RedisSession,
    set_session,
)
from courtlistener.mcp.tools import MCP_TOOLS
from courtlistener.mcp.tools.get_counts_tool import GetCountsTool

pytestmark = pytest.mark.asyncio


def _api_error(status_code: int, detail) -> CourtListenerAPIError:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    return CourtListenerAPIError(status_code, detail, response)


async def _call(name: str, arguments: dict):
    async with Client(create_mcp_server()) as client:
        return await client.call_tool(name, arguments, raise_on_error=False)


class TestListTools:
    async def test_lists_the_registry_unchanged(self):
        async with Client(create_mcp_server()) as client:
            listed = await client.list_tools()

        assert [tool.name for tool in listed] == list(MCP_TOOLS)
        for tool in listed:
            registered = MCP_TOOLS[tool.name]
            assert tool.inputSchema == registered.get_input_schema()
            assert tool.description == type(registered).__doc__
            assert tool.annotations == registered.annotations
            assert tool.title == registered.annotations.title


class TestCallTool:
    async def test_returns_the_tool_result_as_json_text(self):
        result = await _call("get_endpoint_schema", {"endpoint_id": "dockets"})

        assert result.is_error is False
        schema = json.loads(result.content[0].text)
        assert "court" in schema["properties"]

    async def test_validates_arguments_against_the_published_schema(self):
        result = await _call("get_endpoint_schema", {"endpoint": "dockets"})

        assert result.is_error
        text = result.content[0].text
        assert "Invalid arguments for tool 'get_endpoint_schema'" in text
        assert "'endpoint' was unexpected" in text

    async def test_explicit_null_reaches_the_tool_as_unset(self):
        result = await _call(
            "extract_citations",
            {"text": "See Brown v. Board, 347 U.S. 483.", "resolve": None},
        )

        assert result.is_error is False
        assert "347 U.S. 483" in result.content[0].text

    async def test_typed_tool_errors_reach_the_client_unmasked(self):
        error = _api_error(429, {"detail": "Request was throttled."})
        with patch.object(GetCountsTool, "call", side_effect=error):
            result = await _call("get_counts", {"query_id": "abc12345"})

        assert result.is_error
        assert result.content[0].text.startswith("Rate limit exceeded")
        assert "get_api_usage" in result.content[0].text

    async def test_unexpected_exceptions_are_wrapped_by_fastmcp(self):
        with patch.object(GetCountsTool, "call", side_effect=ValueError("x")):
            result = await _call("get_counts", {"query_id": "abc12345"})

        assert result.is_error
        assert result.content[0].text == "Error calling tool 'get_counts': x"

    async def test_unknown_tool_is_reported(self):
        result = await _call("no_such_tool", {})

        assert result.is_error
        assert "Unknown tool" in result.content[0].text


class TestHttpApp:
    """The HTTP app serves the same tools behind the dual-scheme auth."""

    @pytest.fixture(autouse=True)
    def session(self):
        set_session(InMemorySession())
        yield
        set_session(None)

    @pytest.fixture
    def app(self):
        with (
            patch.object(server_mod, "REDIS_URL", "redis://unused"),
            patch(
                "courtlistener.mcp.auth.verify_api_token",
                new=AsyncMock(return_value={"user_hash": "h"}),
            ),
        ):
            yield server_mod.create_http_app()

    def _http(self, app):
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    async def test_rejects_requests_without_a_credential(self, app):
        async with app.router.lifespan_context(app), self._http(app) as http:
            response = await http.post(
                "/",
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                headers={"Accept": "application/json, text/event-stream"},
            )

        assert response.status_code == 401
        assert "resource_metadata=" in response.headers["www-authenticate"]

    async def test_serves_tools_to_an_api_token_client(self, app):
        def factory(headers=None, timeout=None, auth=None, **kwargs):
            return httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
                headers=headers,
                timeout=timeout,
                auth=auth,
                follow_redirects=True,
            )

        transport = StreamableHttpTransport(
            "http://testserver/",
            headers={"Authorization": "Token cl-api-token"},
            httpx_client_factory=factory,
        )
        async with (
            app.router.lifespan_context(app),
            Client(transport) as client,
        ):
            listed = await client.list_tools()
            result = await client.call_tool(
                "get_endpoint_schema", {"endpoint_id": "courts"}
            )

        assert [tool.name for tool in listed] == list(MCP_TOOLS)
        assert "id" in json.loads(result.content[0].text)["properties"]

    async def test_health_reports_the_session_store(self, app):
        session = RedisSession("redis://example.test:6379")
        session._client = MagicMock(ping=AsyncMock(return_value=True))
        set_session(session)

        async with app.router.lifespan_context(app), self._http(app) as http:
            response = await http.get("/health")

        body = response.json()
        assert body["status"] == "healthy"
        assert body["services"] == {"mcp": True, "redis": True}

    async def test_health_reports_postgres_when_configured(self, app):
        session = RedisSession("redis://example.test:6379")
        session._client = MagicMock(ping=AsyncMock(return_value=True))
        set_session(session)
        conn = MagicMock(execute=AsyncMock(), close=AsyncMock())
        probe = AsyncMock(return_value=None)

        bodies = {}
        for label, connect in (
            ("up", AsyncMock(return_value=conn)),
            ("down", AsyncMock(side_effect=OSError("refused"))),
        ):
            probe.side_effect = None if label == "up" else OSError("refused")
            with (
                patch.object(server_mod, "POSTGRES_CONFIGURED", True),
                patch.object(storage_mod, "PGHOST", "db.example.test"),
                patch.object(storage_mod, "PGPASSWORD", "pa%41ss"),
                patch.object(storage_mod.asyncpg, "connect", new=connect),
                patch.object(
                    storage_mod,
                    "get_oauth_store",
                    return_value=MagicMock(get=probe),
                ),
            ):
                async with (
                    app.router.lifespan_context(app),
                    self._http(app) as http,
                ):
                    bodies[label] = (await http.get("/health")).json()

        assert bodies["up"]["status"] == "healthy"
        assert bodies["up"]["services"]["postgres"] is True
        assert bodies["up"]["config"]["oauth_store"] is True
        assert bodies["down"]["status"] == "unhealthy"
        assert bodies["down"]["services"]["postgres"] is False
        assert bodies["down"]["config"]["oauth_store"] is False
        assert connect.await_args.kwargs["host"] == "db.example.test"
        assert connect.await_args.kwargs["password"] == "pa%41ss"
        assert probe.await_args.kwargs == {
            "key": "probe",
            "collection": "health",
        }

    async def test_health_reports_a_missing_store_schema(self, app):
        session = RedisSession("redis://example.test:6379")
        session._client = MagicMock(ping=AsyncMock(return_value=True))
        set_session(session)
        conn = MagicMock(execute=AsyncMock(), close=AsyncMock())
        store = MagicMock(
            get=AsyncMock(side_effect=ValueError("Table does not exist"))
        )
        with (
            patch.object(server_mod, "POSTGRES_CONFIGURED", True),
            patch.object(
                storage_mod.asyncpg,
                "connect",
                new=AsyncMock(return_value=conn),
            ),
            patch.object(storage_mod, "get_oauth_store", return_value=store),
        ):
            async with (
                app.router.lifespan_context(app),
                self._http(app) as http,
            ):
                body = (await http.get("/health")).json()

        assert body["status"] == "healthy"
        assert body["services"] == {
            "mcp": True,
            "redis": True,
            "postgres": True,
        }
        assert body["config"]["oauth_store"] is False

    async def test_health_reports_whether_the_oauth_client_is_configured(
        self, app
    ):
        bodies = {}
        for label, client_id in (
            ("set", "7djcaiT8" + "x" * 32),
            ("unset", None),
        ):
            with (
                patch.object(server_mod, "OAUTH_CLIENT_ID", client_id),
                patch.object(server_mod, "OAUTH_CLIENT_SECRET", "s3cret"),
            ):
                async with (
                    app.router.lifespan_context(app),
                    self._http(app) as http,
                ):
                    bodies[label] = (await http.get("/health")).json()

        assert bodies["set"]["config"] == {"oauth_client": True}
        assert bodies["unset"]["config"] == {"oauth_client": False}
        assert bodies["unset"]["status"] == "healthy"
