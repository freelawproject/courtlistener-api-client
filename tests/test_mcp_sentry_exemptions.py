"""Sentry exemption for triaged known-noise tool errors.

Routine 429 throttling raises ``SentryExemptToolError``, which the
``before_send`` hook drops. Everything else — including 401 session
expiry and upstream 5xx — still reports to Sentry.
"""

import sys
from unittest.mock import MagicMock

import httpx
import pytest
from fastmcp.exceptions import ToolError

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.exceptions import (
    SentryExemptToolError,
    before_send,
)
from courtlistener.mcp.middleware import ToolHandlerMiddleware
from courtlistener.mcp.tools.mcp_tool import MCPTool


def _api_error(status_code: int, detail) -> CourtListenerAPIError:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    return CourtListenerAPIError(status_code, detail, response)


async def _call_tool_raising(monkeypatch, exc):
    class FakeTool(MCPTool):
        name = "fake_tool"

        def get_input_schema(self) -> dict:
            return {"type": "object", "properties": {}}

        async def __call__(self, arguments, ctx):
            raise exc

    monkeypatch.setattr(
        "courtlistener.mcp.middleware.MCP_TOOLS", {"fake_tool": FakeTool()}
    )
    context = MagicMock()
    context.message.name = "fake_tool"
    context.message.arguments = {}
    context.fastmcp_context = MagicMock()
    middleware = ToolHandlerMiddleware()
    return await middleware.on_call_tool(context, call_next=MagicMock())


class TestMiddlewareErrorClassification:
    @pytest.mark.asyncio
    async def test_429_raises_sentry_exempt_error(self, monkeypatch):
        error = _api_error(
            429, {"detail": "Request was throttled. Rate limit exceeded."}
        )
        with pytest.raises(SentryExemptToolError) as excinfo:
            await _call_tool_raising(monkeypatch, error)
        assert "Rate limit exceeded" in str(excinfo.value)
        assert "donate.free.law" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_401_still_reports(self, monkeypatch):
        error = _api_error(401, {"detail": "Invalid token."})
        with pytest.raises(ToolError) as excinfo:
            await _call_tool_raising(monkeypatch, error)
        assert not isinstance(excinfo.value, SentryExemptToolError)

    @pytest.mark.asyncio
    async def test_upstream_500_still_reports(self, monkeypatch):
        error = _api_error(500, {"detail": "Internal Server Error."})
        with pytest.raises(ToolError) as excinfo:
            await _call_tool_raising(monkeypatch, error)
        assert not isinstance(excinfo.value, SentryExemptToolError)


class TestBeforeSend:
    def _hint_for(self, exc: BaseException) -> dict:
        try:
            raise exc
        except BaseException:
            return {"exc_info": sys.exc_info()}

    def test_drops_exempt_errors(self):
        event = {"event_id": "abc"}
        hint = self._hint_for(SentryExemptToolError("Rate limit exceeded"))
        assert before_send(event, hint) is None

    def test_keeps_plain_tool_errors(self):
        event = {"event_id": "abc"}
        hint = self._hint_for(ToolError("CourtListener API error"))
        assert before_send(event, hint) is event

    def test_keeps_events_without_exc_info(self):
        event = {"event_id": "abc"}
        assert before_send(event, {}) is event


class TestValidationErrorFingerprint:
    """ValidationErrors get partitioned by model + failing field so the
    old monolithic bucket (Sentry MCP-G) splits into per-field issues.
    """

    def _validation_error(self, **kwargs):
        from pydantic import ValidationError

        from courtlistener.models.endpoints.opinion_search import (
            OpinionSearchEndpoint,
        )

        try:
            OpinionSearchEndpoint(type="o", **kwargs)
        except ValidationError as exc:
            return exc
        raise AssertionError("expected ValidationError")

    def test_fingerprint_includes_model_and_field(self):
        from courtlistener.mcp.exceptions import validation_error_fingerprint

        exc = self._validation_error(court="njsupct")
        assert validation_error_fingerprint(exc) == [
            "{{ default }}",
            "OpinionSearchEndpoint",
            "court",
        ]

    def test_different_fields_get_different_fingerprints(self):
        from courtlistener.mcp.exceptions import validation_error_fingerprint

        court = validation_error_fingerprint(
            self._validation_error(court="njsupct")
        )
        order_by = validation_error_fingerprint(
            self._validation_error(order_by="relevance desc")
        )
        assert court != order_by

    def test_before_send_sets_fingerprint(self):
        from courtlistener.mcp.exceptions import before_send

        exc = self._validation_error(court="njsupct")
        event = {}
        result = before_send(event, {"exc_info": (type(exc), exc, None)})
        assert result is event
        assert result["fingerprint"] == [
            "{{ default }}",
            "OpinionSearchEndpoint",
            "court",
        ]

    def test_before_send_leaves_other_errors_alone(self):
        from courtlistener.mcp.exceptions import before_send

        event = {}
        err = RuntimeError("boom")
        result = before_send(event, {"exc_info": (RuntimeError, err, None)})
        assert result is event
        assert "fingerprint" not in result
