"""Sentry exemption for triaged known-noise tool errors.

Routine 429 throttling raises ``SentryExemptToolError``, which the
``before_send`` hook drops. 401s are split by how the token passed
admission: cache-verified tokens that CL rejects are routine
mid-session rotation (exempt), while freshly-verified tokens that CL
rejects mean the authorization server and API disagree (reported).
Upstream 5xx always reports.
"""

import sys
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastmcp.exceptions import ToolError

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.exceptions import (
    SentryExemptToolError,
    UnauthorizedToolError,
    UpstreamCourtListenerError,
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

    def _fake_access_token(self, monkeypatch, cached):
        token = MagicMock()
        token.token = "tok"
        token.claims = {
            "user_hash": "uh",
            "token_kind": "oauth",
            "cached": cached,
        }
        monkeypatch.setattr(
            "courtlistener.mcp.middleware.get_access_token", lambda: token
        )
        session = MagicMock()
        session.invalidate_token = AsyncMock()
        monkeypatch.setattr(
            "courtlistener.mcp.middleware.get_session", lambda: session
        )
        return session

    @pytest.mark.asyncio
    async def test_401_on_cached_token_is_exempt(self, monkeypatch):
        """Cache-verified token rejected by CL = routine mid-session
        expiry/rotation: cache busted, error exempt from Sentry."""
        session = self._fake_access_token(monkeypatch, cached=True)
        error = _api_error(401, {"detail": "Invalid token."})
        with pytest.raises(SentryExemptToolError) as excinfo:
            await _call_tool_raising(monkeypatch, error)
        assert "retry to re-authenticate" in str(excinfo.value)
        session.invalidate_token.assert_awaited_once_with("tok", "oauth")

    @pytest.mark.asyncio
    async def test_401_on_freshly_verified_token_reports(self, monkeypatch):
        """Fresh userinfo said valid, CL said invalid: AS/API disagree.
        This is the outage signature and must keep reporting."""
        self._fake_access_token(monkeypatch, cached=False)
        error = _api_error(401, {"detail": "Invalid token."})
        with pytest.raises(UnauthorizedToolError) as excinfo:
            await _call_tool_raising(monkeypatch, error)
        assert excinfo.value.tool_name == "fake_tool"

    @pytest.mark.asyncio
    async def test_401_without_token_context_reports(self, monkeypatch):
        """No access token in context (can't tell cached from fresh):
        report, conservatively."""
        error = _api_error(401, {"detail": "Invalid token."})
        with pytest.raises(UnauthorizedToolError):
            await _call_tool_raising(monkeypatch, error)

    @pytest.mark.asyncio
    async def test_upstream_500_raises_typed_error(self, monkeypatch):
        error = _api_error(500, {"detail": "Internal Server Error."})
        with pytest.raises(UpstreamCourtListenerError) as excinfo:
            await _call_tool_raising(monkeypatch, error)
        assert excinfo.value.tool_name == "fake_tool"
        assert excinfo.value.status == "500"

    @pytest.mark.asyncio
    async def test_transport_failure_raises_typed_error(self, monkeypatch):
        error = httpx.ConnectError("[Errno 104] Connection reset by peer")
        with pytest.raises(UpstreamCourtListenerError) as excinfo:
            await _call_tool_raising(monkeypatch, error)
        assert excinfo.value.status == "connection"

    @pytest.mark.asyncio
    async def test_invalid_fields_maps_to_argument_validation(
        self, monkeypatch
    ):
        """The library's fields check is argument validation the input
        schema can't express; the middleware reclassifies it so it
        lands in the tool-argument Sentry issue."""
        from courtlistener.exceptions import InvalidFieldsError
        from courtlistener.mcp.exceptions import ToolArgumentValidationError

        error = InvalidFieldsError("Invalid fields: ['case_nam'].")
        with pytest.raises(ToolArgumentValidationError) as excinfo:
            await _call_tool_raising(monkeypatch, error)
        assert excinfo.value.tool_name == "fake_tool"
        assert excinfo.value.argument_names == ["fields"]
        assert "case_nam" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_4xx_stays_plain_tool_error(self, monkeypatch):
        error = _api_error(404, {"detail": "Not found."})
        with pytest.raises(ToolError) as excinfo:
            await _call_tool_raising(monkeypatch, error)
        assert not isinstance(excinfo.value, UpstreamCourtListenerError)
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
    """All ValidationErrors share one issue; `model` and `field` tags
    carry the breakdown for the issue-page tag view and dashboards.
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

    def test_before_send_sets_fingerprint_and_tags(self):
        from courtlistener.mcp.exceptions import before_send

        exc = self._validation_error(court="njsupct")
        event = {}
        result = before_send(event, {"exc_info": (type(exc), exc, None)})
        assert result is event
        assert result["fingerprint"] == ["endpoint-model-validation"]
        assert result["tags"] == {
            "model": "OpinionSearchEndpoint",
            "field": "court",
        }

    def test_multiple_fields_join_in_field_tag(self):
        from courtlistener.mcp.exceptions import before_send

        exc = self._validation_error(
            court="njsupct", order_by="relevance desc"
        )
        event = {}
        before_send(event, {"exc_info": (type(exc), exc, None)})
        assert event["tags"]["field"] == "court,order_by"

    def test_existing_tags_are_preserved(self):
        from courtlistener.mcp.exceptions import before_send

        exc = self._validation_error(court="njsupct")
        event = {"tags": {"release": "1.0"}}
        before_send(event, {"exc_info": (type(exc), exc, None)})
        assert event["tags"]["release"] == "1.0"
        assert event["tags"]["model"] == "OpinionSearchEndpoint"

    def test_before_send_leaves_other_errors_alone(self):
        from courtlistener.mcp.exceptions import before_send

        event = {}
        err = RuntimeError("boom")
        result = before_send(event, {"exc_info": (RuntimeError, err, None)})
        assert result is event
        assert "fingerprint" not in result


class TestToolArgumentFingerprint:
    """All argument-schema failures share one issue; `tool` and `field`
    tags carry the breakdown. The error stays a ToolError subclass, so
    the model-facing message is unchanged.
    """

    def _error_for(self, tool, arguments):
        from courtlistener.mcp.exceptions import ToolArgumentValidationError
        from courtlistener.mcp.tools import MCP_TOOLS

        with pytest.raises(ToolArgumentValidationError) as exc_info:
            MCP_TOOLS[tool].validate_arguments(arguments)
        return exc_info.value

    def test_unexpected_property_names_the_argument(self):
        # The historical MCP-2H sample: models passing call_endpoint's
        # `query` shape to search. error.path is empty for
        # additionalProperties, so names are recovered from arguments.
        exc = self._error_for("search", {"type": "o", "query": {"q": "x"}})
        assert exc.tool_name == "search"
        assert exc.argument_names == ["query"]
        assert isinstance(exc, ToolError)

    def test_missing_required_names_the_argument(self):
        # `required` violations also have an empty error.path; the
        # missing names come from the schema's required list.
        exc = self._error_for("search", {"q": "test"})
        assert exc.argument_names == ["type"]

    def test_bad_value_names_the_argument(self):
        exc = self._error_for("search", {"type": "o", "fields": 123})
        assert exc.argument_names == ["fields"]

    def test_before_send_sets_fingerprint_and_tags(self):
        from courtlistener.mcp.exceptions import before_send

        exc = self._error_for("search", {"type": "o", "query": {}})
        event = {}
        result = before_send(event, {"exc_info": (type(exc), exc, None)})
        assert result is event
        assert result["fingerprint"] == ["tool-argument-validation"]
        assert result["tags"] == {"tool": "search", "field": "query"}

    def test_multiple_arguments_join_in_field_tag(self):
        from courtlistener.mcp.exceptions import before_send

        exc = self._error_for("search", {"query": {}, "fields": 123})
        event = {}
        before_send(event, {"exc_info": (type(exc), exc, None)})
        assert event["tags"]["tool"] == "search"
        assert event["tags"]["field"] == "fields,query,type"


class TestUnauthorizedFingerprint:
    """All fresh-token 401 rejections share one issue; the chained
    CourtListenerAPIError's stack trace differs per tool and client
    code path, which would otherwise split default grouping into a
    bucket per call path. A `tool` tag carries the breakdown.
    """

    def test_before_send_sets_fingerprint_and_tags(self):
        exc = UnauthorizedToolError("unauthorized", tool_name="search")
        event = {}
        result = before_send(event, {"exc_info": (type(exc), exc, None)})
        assert result is event
        assert result["fingerprint"] == ["unauthorized-tool-call"]
        assert result["tags"] == {"tool": "search"}

    def test_different_tools_share_a_fingerprint(self):
        def fingerprint(tool):
            exc = UnauthorizedToolError("unauthorized", tool_name=tool)
            event = {}
            before_send(event, {"exc_info": (type(exc), exc, None)})
            return event["fingerprint"]

        assert fingerprint("search") == fingerprint("analyze_citations")


class TestSessionDataFingerprint:
    """Stale query/job ids get their own issue, separate from the
    tool-argument bucket: they're usually TTL expiry, and a spike
    points at Redis/session-store health rather than model behavior.
    """

    def test_before_send_sets_fingerprint_and_tags(self):
        from courtlistener.mcp.exceptions import SessionDataNotFoundError

        exc = SessionDataNotFoundError(
            "Query ID 'abc123' not found.",
            tool_name="get_more_results",
            argument_name="query_id",
        )
        event = {}
        result = before_send(event, {"exc_info": (type(exc), exc, None)})
        assert result is event
        assert result["fingerprint"] == ["session-data-not-found"]
        assert result["tags"] == {
            "tool": "get_more_results",
            "field": "query_id",
        }

    def test_query_and_job_ids_share_a_fingerprint(self):
        from courtlistener.mcp.exceptions import SessionDataNotFoundError

        def fingerprint(tool, argument_name):
            exc = SessionDataNotFoundError(
                "not found", tool_name=tool, argument_name=argument_name
            )
            event = {}
            before_send(event, {"exc_info": (type(exc), exc, None)})
            return event["fingerprint"]

        assert fingerprint("get_counts", "query_id") == fingerprint(
            "resume_citation_analysis", "job_id"
        )


class TestUpstreamFingerprint:
    """Upstream failures are keyed by status alone: a 500 spike and a
    502 spike are different upstream conditions, but which tool tripped
    one is irrelevant and lives in the `tool` tag instead.
    """

    def _fingerprint(self, tool, status):
        exc = UpstreamCourtListenerError(
            "upstream", tool_name=tool, status=status
        )
        event = {}
        before_send(event, {"exc_info": (type(exc), exc, None)})
        return event

    def test_before_send_sets_fingerprint_and_tags(self):
        event = self._fingerprint("search", "502")
        assert event["fingerprint"] == ["courtlistener-upstream", "502"]
        assert event["tags"] == {"tool": "search", "upstream_status": "502"}

    def test_different_tools_share_a_fingerprint(self):
        assert (
            self._fingerprint("search", "502")["fingerprint"]
            == self._fingerprint("read_document", "502")["fingerprint"]
        )

    def test_different_statuses_get_different_fingerprints(self):
        assert (
            self._fingerprint("search", "500")["fingerprint"]
            != self._fingerprint("search", "502")["fingerprint"]
        )
