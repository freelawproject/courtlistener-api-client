"""Friendly error translation for mutation MCP tools.

Covers the regression in issue #120: ``delete_search_alert``,
``subscribe_to_docket_alert`` and ``create_search_alert`` previously
leaked raw ``HTTP 4xx: {...}`` strings (Django internals) to MCP
clients. They now catch the well-defined client-error cases and
return clean messages, while still bubbling genuine server errors.
"""

from unittest.mock import MagicMock

import httpx
import pytest

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.tools.create_search_alert_tool import (
    CreateSearchAlertTool,
)
from courtlistener.mcp.tools.delete_search_alert_tool import (
    DeleteSearchAlertTool,
)
from courtlistener.mcp.tools.subscribe_to_docket_alert_tool import (
    SubscribeToDocketAlertTool,
)


def _api_error(status_code: int, detail) -> CourtListenerAPIError:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    return CourtListenerAPIError(status_code, detail, response)


def _client_cm(client):
    """Wrap a mock client in a context manager (for ``with get_client()``)."""
    cm = MagicMock()
    cm.__enter__.return_value = client
    cm.__exit__.return_value = False
    return cm


class TestDeleteSearchAlertErrors:
    @pytest.mark.asyncio
    async def test_missing_id_returns_clean_message(self, monkeypatch):
        client = MagicMock()
        client.alerts.delete.side_effect = _api_error(
            404, {"detail": "No Alert matches the given query."}
        )
        tool = DeleteSearchAlertTool()
        monkeypatch.setattr(tool, "get_client", lambda: _client_cm(client))

        result = await tool({"id": 99999999}, ctx=MagicMock())

        assert result == "No alert found with id 99999999."

    @pytest.mark.asyncio
    async def test_server_error_still_raises(self, monkeypatch):
        client = MagicMock()
        client.alerts.delete.side_effect = _api_error(500, "boom")
        tool = DeleteSearchAlertTool()
        monkeypatch.setattr(tool, "get_client", lambda: _client_cm(client))

        with pytest.raises(CourtListenerAPIError) as exc_info:
            await tool({"id": 1}, ctx=MagicMock())
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_success_path_unchanged(self, monkeypatch):
        client = MagicMock()
        client.alerts.delete.return_value = None
        tool = DeleteSearchAlertTool()
        monkeypatch.setattr(tool, "get_client", lambda: _client_cm(client))

        result = await tool({"id": 42}, ctx=MagicMock())

        assert result == "Deleted search alert 42."


class TestSubscribeToDocketAlertErrors:
    @pytest.mark.asyncio
    async def test_already_subscribed_dict_passes_through(self, monkeypatch):
        """SDK now handles the unique-set 400 by returning the existing alert
        dict with ``already_subscribed=True``. The MCP tool should forward
        that dict unchanged (covered in SDK tests; this just locks in
        the boundary contract).
        """
        existing = {
            "id": 7,
            "docket": 73209323,
            "alert_type": 1,
            "already_subscribed": True,
        }
        client = MagicMock()
        client.docket_alerts.subscribe.return_value = existing
        tool = SubscribeToDocketAlertTool()
        monkeypatch.setattr(tool, "get_client", lambda: _client_cm(client))

        result = await tool({"docket": 73209323}, ctx=MagicMock())

        assert result == existing

    @pytest.mark.asyncio
    async def test_other_400_returns_clean_message(self, monkeypatch):
        detail = {"docket": ["Invalid pk - object does not exist."]}
        client = MagicMock()
        client.docket_alerts.subscribe.side_effect = _api_error(400, detail)
        tool = SubscribeToDocketAlertTool()
        monkeypatch.setattr(tool, "get_client", lambda: _client_cm(client))

        result = await tool({"docket": 1}, ctx=MagicMock())

        assert isinstance(result, str)
        assert result.startswith("Could not subscribe to docket 1:")
        # Importantly: no "HTTP 400" prefix leak.
        assert "HTTP 400" not in result

    @pytest.mark.asyncio
    async def test_server_error_still_raises(self, monkeypatch):
        client = MagicMock()
        client.docket_alerts.subscribe.side_effect = _api_error(500, "boom")
        tool = SubscribeToDocketAlertTool()
        monkeypatch.setattr(tool, "get_client", lambda: _client_cm(client))

        with pytest.raises(CourtListenerAPIError) as exc_info:
            await tool({"docket": 1}, ctx=MagicMock())
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_success_path_returns_alert_dict(self, monkeypatch):
        alert = {"id": 1, "docket": 1, "alert_type": 1}
        client = MagicMock()
        client.docket_alerts.subscribe.return_value = alert
        tool = SubscribeToDocketAlertTool()
        monkeypatch.setattr(tool, "get_client", lambda: _client_cm(client))

        result = await tool({"docket": 1}, ctx=MagicMock())

        assert result == alert


class TestCreateSearchAlertErrors:
    @pytest.mark.asyncio
    async def test_bad_request_returns_clean_message(self, monkeypatch):
        client = MagicMock()
        client.alerts.create.side_effect = _api_error(
            400, {"query": ["Invalid query syntax."]}
        )
        tool = CreateSearchAlertTool()
        monkeypatch.setattr(tool, "get_client", lambda: _client_cm(client))

        result = await tool(
            {"name": "x", "query": "q=foo", "rate": "off"},
            ctx=MagicMock(),
        )

        assert isinstance(result, str)
        assert result.startswith("Could not create search alert:")
        assert "HTTP 400" not in result

    @pytest.mark.asyncio
    async def test_server_error_still_raises(self, monkeypatch):
        client = MagicMock()
        client.alerts.create.side_effect = _api_error(500, "boom")
        tool = CreateSearchAlertTool()
        monkeypatch.setattr(tool, "get_client", lambda: _client_cm(client))

        with pytest.raises(CourtListenerAPIError) as exc_info:
            await tool(
                {"name": "x", "query": "q=foo", "rate": "off"},
                ctx=MagicMock(),
            )
        assert exc_info.value.status_code == 500
