"""Tests for the get_api_usage MCP tool."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from courtlistener.mcp.tools.get_api_usage_tool import (
    GetApiUsageTool,
    summarize_main_quota,
)


def _row(scope, rate, used, limit, reset_at=None, blocked=False):
    return {
        "scope": scope,
        "rate": rate,
        "used": used,
        "limit": limit,
        "remaining": max(limit - used, 0),
        "window_seconds": 3600,
        "reset_at": reset_at,
        "blocked": blocked,
    }


# Sorted the way the API sorts: closest to its limit first, which puts
# the endpoint's own narrow scope ahead of the one users care about.
PAYLOAD = {
    "current_usage": [
        _row("api_usage", "10/min", 3, 10, "2026-09-14T18:01:00+00:00"),
        _row("user", "5000/hour", 12, 5000, "2026-09-14T18:00:00+00:00"),
        _row("citations", "60/min", 0, 60),
        _row("fetch", "30/min", 0, 30),
    ],
    "historical_usage": {"2026-09-14": 12, "total": 12},
    "membership": None,
}


def _client_cm(client):
    cm = MagicMock()
    cm.__aenter__.return_value = client
    cm.__aexit__.return_value = False
    return cm


def _tool(monkeypatch, payload=PAYLOAD):
    client = AsyncMock()
    client.api_usage.get.return_value = payload
    tool = GetApiUsageTool()
    monkeypatch.setattr(tool, "get_client", lambda: _client_cm(client))
    return tool


class TestGetApiUsage:
    pytestmark = pytest.mark.asyncio

    async def test_groups_scopes_with_user_first(self, monkeypatch):
        result = await _tool(monkeypatch)({}, ctx=MagicMock())

        assert list(result["current_usage"]) == [
            "user",
            "citations",
            "fetch",
            "api_usage",
        ]
        user = result["current_usage"]["user"]
        assert user["limits"] == [PAYLOAD["current_usage"][1]]
        assert "main API quota" in user["description"]
        assert "ignore" in result["current_usage"]["api_usage"]["description"]

    async def test_summary_reads_from_user_scope(self, monkeypatch):
        result = await _tool(monkeypatch)({}, ctx=MagicMock())

        assert result["summary"].startswith("4988 of 5000 API requests")
        assert "5000/hour" in result["summary"]
        assert "10/min" not in result["summary"]

    async def test_passes_history_and_membership_through(self, monkeypatch):
        result = await _tool(monkeypatch)({}, ctx=MagicMock())

        assert result["historical_usage"] == PAYLOAD["historical_usage"]
        assert result["membership"] is None

    async def test_unknown_scope_is_kept(self, monkeypatch):
        payload = {
            **PAYLOAD,
            "current_usage": [_row("future", "1/min", 0, 1)],
        }
        result = await _tool(monkeypatch, payload)({}, ctx=MagicMock())

        assert list(result["current_usage"]) == ["future"]
        assert result["summary"].startswith("No main API quota")


class TestInputSchema:
    def test_rejects_arguments(self):
        with pytest.raises(Exception, match="unexpected"):
            GetApiUsageTool().validate_arguments({"scope": "user"})


class TestSummarizeMainQuota:
    def test_blocked(self):
        text = summarize_main_quota(
            [_row("user", "0/min", 0, 0, blocked=True)]
        )
        assert text.startswith("API access is blocked")

    def test_empty_window(self):
        text = summarize_main_quota([_row("user", "5000/hour", 0, 5000)])
        assert "window is currently empty" in text

    def test_multiple_limits(self):
        text = summarize_main_quota(
            [
                _row("user", "100/hour", 1, 100, "2026-09-14T18:00:00+00:00"),
                _row("user", "1000/day", 1, 1000, "2026-09-15T00:00:00+00:00"),
            ]
        )
        assert "99 of 100" in text
        assert "999 of 1000" in text
