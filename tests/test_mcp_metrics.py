"""Prometheus metrics: per-tool call counter, the active-user gauge,
and the /metrics route."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, call

import httpx
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from prometheus_client import REGISTRY
from pydantic import BaseModel, ValidationError

import courtlistener.mcp.metrics as metrics_mod
from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.exceptions import (
    SessionDataNotFoundError,
    ToolArgumentValidationError,
    UnauthorizedToolError,
    UpstreamCourtListenerError,
)
from courtlistener.mcp.metrics import (
    OUTCOMES,
    ActiveUserMarker,
    active_user_counts,
    error_outcome,
    render_metrics,
    tool_calls_total,
)
from courtlistener.mcp.server import create_mcp_server
from courtlistener.mcp.session import InMemorySession, set_session, utc_today
from courtlistener.mcp.tools.mcp_tool import MCPTool


def _api_error(status_code: int) -> CourtListenerAPIError:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    return CourtListenerAPIError(status_code, {"detail": "x"}, response)


class _Model(BaseModel):
    n: int


def _validation_error() -> ValidationError:
    try:
        _Model(n="x")
    except ValidationError as exc:
        return exc
    raise AssertionError("expected a ValidationError")


def _count(tool: str, outcome: str) -> float:
    value = REGISTRY.get_sample_value(
        "mcp_tool_calls_total", {"tool": tool, "outcome": outcome}
    )
    return value or 0.0


async def _call_tool(tool_name, behavior):
    class FakeTool(MCPTool):
        name: str = tool_name
        annotations: ToolAnnotations = ToolAnnotations(title="Fake")

        def get_input_schema(self) -> dict:
            return {"type": "object", "properties": {}}

        async def call(self, arguments):
            return behavior()

    return await FakeTool().run({})


def _access_token(user_hash="uh", token_kind="oauth"):
    token = MagicMock()
    token.token = "tok"
    token.claims = {"user_hash": user_hash, "token_kind": token_kind}
    return token


class TestOutcomeFor:
    def test_known_tool_errors(self):
        assert (
            error_outcome(ToolArgumentValidationError("m", "t", ["a"]))
            == "validation_error"
        )
        assert error_outcome(_validation_error()) == "validation_error"
        assert (
            error_outcome(SessionDataNotFoundError("m", "t", "a"))
            == "session_data_not_found"
        )
        assert error_outcome(UnauthorizedToolError("m", "t")) == "unauthorized"
        assert (
            error_outcome(UpstreamCourtListenerError("m", "t", "503"))
            == "upstream_error"
        )

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (401, "unauthorized"),
            (429, "rate_limited"),
            (404, "api_error"),
            (502, "upstream_error"),
        ],
    )
    def test_classifies_by_upstream_status(self, status, expected):
        exc = ToolError("wrapped")
        exc.__cause__ = _api_error(status)
        assert error_outcome(exc) == expected

    def test_unknown_exception_is_error(self):
        assert error_outcome(RuntimeError("boom")) == "error"

    def test_every_outcome_is_declared(self):
        seen = {
            error_outcome(ToolArgumentValidationError("m", "t", ["a"])),
            error_outcome(_validation_error()),
            error_outcome(SessionDataNotFoundError("m", "t", "a")),
            error_outcome(UnauthorizedToolError("m", "t")),
            error_outcome(UpstreamCourtListenerError("m", "t", "503")),
            error_outcome(RuntimeError()),
        }
        for status in (401, 429, 404, 502):
            exc = ToolError("wrapped")
            exc.__cause__ = _api_error(status)
            seen.add(error_outcome(exc))
        assert seen | {"ok"} == set(OUTCOMES)


class TestToolCallCounter:
    @pytest.mark.asyncio
    async def test_success_counts_ok(self):
        before = _count("metrics_ok_tool", "ok")
        await _call_tool("metrics_ok_tool", lambda: {"a": 1})
        assert _count("metrics_ok_tool", "ok") == before + 1

    @pytest.mark.asyncio
    async def test_rate_limit_counts_rate_limited(self):
        def raise_429():
            raise _api_error(429)

        before = _count("metrics_429_tool", "rate_limited")
        with pytest.raises(ToolError):
            await _call_tool("metrics_429_tool", raise_429)
        assert _count("metrics_429_tool", "rate_limited") == before + 1
        assert _count("metrics_429_tool", "ok") == 0

    @pytest.mark.asyncio
    async def test_upstream_failure_counts_upstream_error(self):
        def raise_503():
            raise _api_error(503)

        before = _count("metrics_503_tool", "upstream_error")
        with pytest.raises(UpstreamCourtListenerError):
            await _call_tool("metrics_503_tool", raise_503)
        assert _count("metrics_503_tool", "upstream_error") == before + 1

    @pytest.mark.asyncio
    async def test_unknown_tool_is_not_counted(self):
        async with Client(create_mcp_server()) as client:
            result = await client.call_tool(
                "no_such_tool", {}, raise_on_error=False
            )
        assert result.is_error
        for outcome in OUTCOMES:
            assert _count("no_such_tool", outcome) == 0


class TestMetricsRoute:
    @pytest.mark.asyncio
    async def test_render_metrics_exposes_counter(self):
        tool_calls_total.labels(tool="metrics_render_tool", outcome="ok")
        body, content_type = await render_metrics()
        assert content_type.startswith("text/plain")
        assert b"mcp_tool_calls_total" in body

    @pytest.mark.asyncio
    async def test_metrics_route_serves_scrape(self):
        app = create_mcp_server().http_app(path="/", stateless_http=True)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get("/metrics")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert "mcp_tool_calls_total" in response.text


class TestActiveUserMarking:
    """``run`` marks the verified user active, once per user, credential,
    and UTC day per process."""

    @pytest.fixture(autouse=True)
    def fresh_marker(self, monkeypatch):
        monkeypatch.setattr(
            metrics_mod, "active_user_marker", ActiveUserMarker()
        )

    @pytest.fixture
    def session(self, monkeypatch):
        session = MagicMock(mark_active=AsyncMock(return_value=True))
        monkeypatch.setattr(metrics_mod, "get_session", lambda: session)
        return session

    def _authenticate(self, monkeypatch, token):
        monkeypatch.setattr(metrics_mod, "get_access_token", lambda: token)

    @pytest.mark.asyncio
    async def test_marks_once_per_user_per_day(self, monkeypatch, session):
        self._authenticate(monkeypatch, _access_token())
        await _call_tool("metrics_active_tool", lambda: {"a": 1})
        await _call_tool("metrics_active_tool", lambda: {"a": 1})
        session.mark_active.assert_awaited_once_with(
            "uh", "oauth", utc_today()
        )

    @pytest.mark.asyncio
    async def test_failed_calls_mark_too(self, monkeypatch, session):
        def boom():
            raise RuntimeError("boom")

        self._authenticate(monkeypatch, _access_token())
        with pytest.raises(RuntimeError):
            await _call_tool("metrics_active_tool", boom)
        session.mark_active.assert_awaited_once_with(
            "uh", "oauth", utc_today()
        )

    @pytest.mark.asyncio
    async def test_each_user_and_credential_marks(self, monkeypatch, session):
        today = utc_today()
        for token in (
            _access_token("a", "oauth"),
            _access_token("a", "api_token"),
            _access_token("b", "oauth"),
            _access_token("b", "oauth"),
        ):
            self._authenticate(monkeypatch, token)
            await _call_tool("metrics_active_tool", lambda: {"a": 1})
        assert session.mark_active.await_args_list == [
            call("a", "oauth", today),
            call("a", "api_token", today),
            call("b", "oauth", today),
        ]

    @pytest.mark.asyncio
    async def test_a_new_utc_day_marks_again(self, monkeypatch, session):
        today = utc_today()
        tomorrow = today + timedelta(days=1)
        self._authenticate(monkeypatch, _access_token())
        monkeypatch.setattr(metrics_mod, "utc_today", lambda: today)
        await _call_tool("metrics_active_tool", lambda: {"a": 1})
        monkeypatch.setattr(metrics_mod, "utc_today", lambda: tomorrow)
        await _call_tool("metrics_active_tool", lambda: {"a": 1})
        await _call_tool("metrics_active_tool", lambda: {"a": 1})
        assert session.mark_active.await_args_list == [
            call("uh", "oauth", today),
            call("uh", "oauth", tomorrow),
        ]

    @pytest.mark.asyncio
    async def test_a_degraded_write_is_retried(self, monkeypatch, session):
        session.mark_active.side_effect = [False, True, True]
        self._authenticate(monkeypatch, _access_token())
        for _ in range(3):
            await _call_tool("metrics_active_tool", lambda: {"a": 1})
        assert session.mark_active.await_count == 2

    @pytest.mark.asyncio
    async def test_no_access_token_is_a_noop(self, monkeypatch, session):
        self._authenticate(monkeypatch, None)
        await _call_tool("metrics_active_tool", lambda: {"a": 1})
        session.mark_active.assert_not_awaited()


class TestActiveUsersGauge:
    @pytest.fixture(autouse=True)
    def session(self):
        session = InMemorySession()
        set_session(session)
        yield session
        set_session(None)

    @pytest.mark.asyncio
    async def test_render_metrics_exposes_the_gauge(self, session):
        today = utc_today()
        await session.mark_active("u1", "oauth", today)
        await session.mark_active("u2", "oauth", today)
        for n in range(5):
            await session.mark_active(
                f"a{n}", "api_token", today - timedelta(days=20)
            )
        body, _ = await render_metrics()
        text = body.decode()
        assert "# TYPE mcp_active_users gauge" in text
        assert 'mcp_active_users{credential="oauth",window="1d"} 2.0' in text
        assert (
            'mcp_active_users{credential="api_token",window="30d"} 5.0' in text
        )

    @pytest.mark.asyncio
    async def test_gauge_stays_off_the_default_registry(self, session):
        await session.mark_active("u1", "oauth", utc_today())
        body, _ = await render_metrics()
        assert b"mcp_active_users" in body
        assert b"mcp_tool_calls_total" in body
        assert (
            REGISTRY.get_sample_value(
                "mcp_active_users", {"window": "1d", "credential": "oauth"}
            )
            is None
        )

    @pytest.mark.asyncio
    async def test_gauge_is_omitted_when_the_store_is_unavailable(self):
        """A gap is honest; zeros would read as "no users"."""
        set_session(MagicMock(active_users=AsyncMock(return_value=None)))
        body, _ = await render_metrics()
        assert b"mcp_active_users" not in body
        assert b"mcp_tool_calls_total" in body

    @pytest.mark.asyncio
    async def test_counts_cover_every_window_and_credential(self, session):
        today = utc_today()
        await session.mark_active("u1", "oauth", today)
        await session.mark_active("u2", "oauth", today - timedelta(days=3))
        await session.mark_active(
            "u3", "api_token", today - timedelta(days=20)
        )
        assert await active_user_counts(session, today) == {
            ("1d", "oauth"): 1,
            ("1d", "api_token"): 0,
            ("7d", "oauth"): 2,
            ("7d", "api_token"): 0,
            ("30d", "oauth"): 2,
            ("30d", "api_token"): 1,
        }

    @pytest.mark.asyncio
    async def test_metrics_route_reports_active_users(self, session):
        today = utc_today()
        await session.mark_active("u1", "oauth", today)
        await session.mark_active("u2", "oauth", today - timedelta(days=3))
        await session.mark_active("u3", "api_token", today)
        app = create_mcp_server().http_app(path="/", stateless_http=True)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get("/metrics")
        text = response.text
        assert 'mcp_active_users{credential="oauth",window="1d"} 1.0' in text
        assert 'mcp_active_users{credential="oauth",window="7d"} 2.0' in text
        assert (
            'mcp_active_users{credential="api_token",window="1d"} 1.0' in text
        )
        assert (
            'mcp_active_users{credential="api_token",window="30d"} 1.0' in text
        )
