"""Tests for the pray_for_document and withdraw_prayer MCP tools."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.tools.pray_for_document_tool import (
    PrayForDocumentTool,
)
from courtlistener.mcp.tools.withdraw_prayer_tool import WithdrawPrayerTool

pytestmark = pytest.mark.asyncio

UNAVAILABLE = {
    "id": 112,
    "is_available": False,
    "document_number": "21",
    "description": "Order",
}
PRAYER = {"id": 7, "status": 1, "recap_document": 112}


def _api_error(status_code: int, detail) -> CourtListenerAPIError:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    return CourtListenerAPIError(status_code, detail, response)


def _client_cm(client):
    cm = MagicMock()
    cm.__aenter__.return_value = client
    cm.__aexit__.return_value = False
    return cm


async def _aiter(items):
    for item in items:
        yield item


def _pray_tool(monkeypatch, document=UNAVAILABLE, create=PRAYER):
    client = AsyncMock()
    if isinstance(document, Exception):
        client.recap_documents.get.side_effect = document
    else:
        client.recap_documents.get.return_value = document
    if isinstance(create, Exception):
        client.prayers.create.side_effect = create
    else:
        client.prayers.create.return_value = create
    tool = PrayForDocumentTool()
    monkeypatch.setattr(tool, "get_client", lambda: _client_cm(client))
    return tool, client


class TestPrayForDocument:
    async def test_success_returns_prayer_with_document_context(
        self, monkeypatch
    ):
        tool, client = _pray_tool(monkeypatch)

        result = await tool({"recap_document_id": 112}, ctx=MagicMock())

        client.prayers.create.assert_awaited_once_with(112)
        assert result["id"] == 7
        assert result["recap_document"] == 112
        assert result["document_number"] == "21"
        assert result["description"] == "Order"
        assert "emailed" in result["message"]

    async def test_checks_availability_with_narrow_fields(self, monkeypatch):
        tool, client = _pray_tool(monkeypatch)

        await tool({"recap_document_id": 112}, ctx=MagicMock())

        _, kwargs = client.recap_documents.get.await_args
        assert "is_available" in kwargs["fields"]
        assert "plain_text" not in kwargs["fields"]

    async def test_available_document_skips_prayer(self, monkeypatch):
        tool, client = _pray_tool(
            monkeypatch, document={**UNAVAILABLE, "is_available": True}
        )

        result = await tool({"recap_document_id": 112}, ctx=MagicMock())

        client.prayers.create.assert_not_awaited()
        assert "already available" in result
        assert "read_document" in result

    async def test_missing_document_returns_clean_message(self, monkeypatch):
        tool, client = _pray_tool(
            monkeypatch, document=_api_error(404, {"detail": "Not found."})
        )

        result = await tool({"recap_document_id": 1}, ctx=MagicMock())

        client.prayers.create.assert_not_awaited()
        assert result == "No RECAP document found with id 1."

    async def test_duplicate_returns_already_praying(self, monkeypatch):
        detail = {
            "non_field_errors": [
                "The fields user, recap_document must make a unique set."
            ]
        }
        tool, _ = _pray_tool(monkeypatch, create=_api_error(400, detail))

        result = await tool({"recap_document_id": 112}, ctx=MagicMock())

        assert result.startswith("You are already praying for RECAP document")
        assert "HTTP 400" not in result

    async def test_quota_400_returns_clean_message(self, monkeypatch):
        detail = {
            "non_field_errors": [
                "You have reached the maximum number of prayers (5) "
                "allowed in the last 24 hours."
            ]
        }
        tool, _ = _pray_tool(monkeypatch, create=_api_error(400, detail))

        result = await tool({"recap_document_id": 112}, ctx=MagicMock())

        assert result.startswith("Could not pray for RECAP document 112:")
        assert "maximum number of prayers" in result
        assert "HTTP 400" not in result

    async def test_server_error_still_raises(self, monkeypatch):
        tool, _ = _pray_tool(monkeypatch, create=_api_error(500, "boom"))

        with pytest.raises(CourtListenerAPIError) as exc_info:
            await tool({"recap_document_id": 112}, ctx=MagicMock())
        assert exc_info.value.status_code == 500

    async def test_document_lookup_server_error_still_raises(
        self, monkeypatch
    ):
        tool, _ = _pray_tool(monkeypatch, document=_api_error(503, "down"))

        with pytest.raises(CourtListenerAPIError) as exc_info:
            await tool({"recap_document_id": 112}, ctx=MagicMock())
        assert exc_info.value.status_code == 503


def _withdraw_tool(monkeypatch, existing):
    client = AsyncMock()
    client.prayers.list = MagicMock(return_value=_aiter(existing))
    tool = WithdrawPrayerTool()
    monkeypatch.setattr(tool, "get_client", lambda: _client_cm(client))
    return tool, client


class TestWithdrawPrayer:
    async def test_deletes_pending_prayer_by_document(self, monkeypatch):
        tool, client = _withdraw_tool(monkeypatch, [PRAYER])

        result = await tool({"recap_document_id": 112}, ctx=MagicMock())

        client.prayers.list.assert_called_once_with(recap_document=112)
        client.prayers.delete.assert_awaited_once_with(7)
        assert result == "Withdrew prayer for RECAP document 112."

    async def test_no_prayer_returns_clean_message(self, monkeypatch):
        tool, client = _withdraw_tool(monkeypatch, [])

        result = await tool({"recap_document_id": 112}, ctx=MagicMock())

        client.prayers.delete.assert_not_awaited()
        assert result == "No pending prayer found for RECAP document 112."
