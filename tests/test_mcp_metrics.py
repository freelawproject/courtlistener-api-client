"""Prometheus metrics: per-tool call counter and the /metrics route."""

from unittest.mock import MagicMock

import httpx
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from prometheus_client import REGISTRY
from pydantic import BaseModel, ValidationError

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.exceptions import (
    SessionDataNotFoundError,
    ToolArgumentValidationError,
    UnauthorizedToolError,
    UpstreamCourtListenerError,
)
from courtlistener.mcp.metrics import (
    OUTCOMES,
    error_outcome,
    render_metrics,
    tool_calls_total,
)
from courtlistener.mcp.server import create_mcp_server
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
    def test_render_metrics_exposes_counter(self):
        tool_calls_total.labels(tool="metrics_render_tool", outcome="ok")
        body, content_type = render_metrics()
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
