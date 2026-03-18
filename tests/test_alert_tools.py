"""Tests for alert MCP tools."""

import json
from unittest.mock import MagicMock, patch

import pytest

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.tools import MCP_TOOLS
from courtlistener.mcp.tools.create_search_alert_tool import (
    CreateSearchAlertTool,
)
from courtlistener.mcp.tools.delete_search_alert_tool import (
    DeleteSearchAlertTool,
)
from courtlistener.mcp.tools.subscribe_to_docket_alert_tool import (
    SubscribeToDocketAlertTool,
)
from courtlistener.mcp.tools.unsubscribe_from_docket_alert_tool import (
    UnsubscribeFromDocketAlertTool,
)

# ---------------------------------------------------------------------------
# Unit tests – tool registration and schema
# ---------------------------------------------------------------------------


class TestToolRegistration:
    """Verify the tools are properly registered."""

    def test_create_search_alert_registered(self):
        assert "create_search_alert" in MCP_TOOLS

    def test_delete_search_alert_registered(self):
        assert "delete_search_alert" in MCP_TOOLS

    def test_subscribe_to_docket_alert_registered(self):
        assert "subscribe_to_docket_alert" in MCP_TOOLS

    def test_unsubscribe_from_docket_alert_registered(self):
        assert "unsubscribe_from_docket_alert" in MCP_TOOLS


class TestCreateSearchAlertToolSchema:
    def test_get_tool(self):
        tool = CreateSearchAlertTool()
        mcp_tool = tool.get_tool()
        assert mcp_tool.name == "create_search_alert"
        assert mcp_tool.description
        assert mcp_tool.inputSchema

    def test_schema_required_fields(self):
        tool = CreateSearchAlertTool()
        schema = tool.get_input_schema()
        assert set(schema["required"]) == {"name", "query", "rate"}

    def test_schema_properties(self):
        tool = CreateSearchAlertTool()
        schema = tool.get_input_schema()
        props = schema["properties"]
        assert "name" in props
        assert "query" in props
        assert "rate" in props
        assert "alert_type" in props


class TestDeleteSearchAlertToolSchema:
    def test_get_tool(self):
        tool = DeleteSearchAlertTool()
        mcp_tool = tool.get_tool()
        assert mcp_tool.name == "delete_search_alert"
        assert mcp_tool.description
        assert mcp_tool.inputSchema

    def test_schema_required_fields(self):
        tool = DeleteSearchAlertTool()
        schema = tool.get_input_schema()
        assert schema["required"] == ["id"]

    def test_schema_properties(self):
        tool = DeleteSearchAlertTool()
        schema = tool.get_input_schema()
        assert "id" in schema["properties"]
        assert schema["properties"]["id"]["type"] == "integer"


class TestSubscribeToDocketAlertToolSchema:
    def test_get_tool(self):
        tool = SubscribeToDocketAlertTool()
        mcp_tool = tool.get_tool()
        assert mcp_tool.name == "subscribe_to_docket_alert"
        assert mcp_tool.description
        assert mcp_tool.inputSchema

    def test_schema_required_fields(self):
        tool = SubscribeToDocketAlertTool()
        schema = tool.get_input_schema()
        assert schema["required"] == ["docket"]

    def test_schema_properties(self):
        tool = SubscribeToDocketAlertTool()
        schema = tool.get_input_schema()
        assert "docket" in schema["properties"]
        assert schema["properties"]["docket"]["type"] == "integer"


class TestUnsubscribeFromDocketAlertToolSchema:
    def test_get_tool(self):
        tool = UnsubscribeFromDocketAlertTool()
        mcp_tool = tool.get_tool()
        assert mcp_tool.name == "unsubscribe_from_docket_alert"
        assert mcp_tool.description
        assert mcp_tool.inputSchema

    def test_schema_required_fields(self):
        tool = UnsubscribeFromDocketAlertTool()
        schema = tool.get_input_schema()
        assert schema["required"] == ["docket"]


# ---------------------------------------------------------------------------
# Unit tests – tool execution with mocked client
# ---------------------------------------------------------------------------


class TestCreateSearchAlertToolCall:
    @patch.object(CreateSearchAlertTool, "get_client")
    def test_success(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.alerts.create.return_value = {
            "id": 42,
            "name": "Test",
            "query": "q=test",
            "rate": "dly",
        }
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_get_client.return_value = mock_client

        tool = CreateSearchAlertTool()
        result = tool(
            {"name": "Test", "query": "q=test", "rate": "dly"}, {}
        )

        assert not result.isError
        data = json.loads(result.content[0].text)
        assert data["id"] == 42
        assert data["name"] == "Test"

    @patch.object(CreateSearchAlertTool, "get_client")
    def test_api_error(self, mock_get_client):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_client.alerts.create.side_effect = CourtListenerAPIError(
            status_code=400, detail="Bad request", response=mock_response
        )
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_get_client.return_value = mock_client

        tool = CreateSearchAlertTool()
        result = tool(
            {"name": "Test", "query": "q=test", "rate": "dly"}, {}
        )

        assert result.isError
        assert "400" in result.content[0].text


class TestDeleteSearchAlertToolCall:
    @patch.object(DeleteSearchAlertTool, "get_client")
    def test_success(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.alerts.delete.return_value = None
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_get_client.return_value = mock_client

        tool = DeleteSearchAlertTool()
        result = tool({"id": 42}, {})

        assert not result.isError
        assert "42" in result.content[0].text

    @patch.object(DeleteSearchAlertTool, "get_client")
    def test_api_error(self, mock_get_client):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_client.alerts.delete.side_effect = CourtListenerAPIError(
            status_code=404, detail="Not found", response=mock_response
        )
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_get_client.return_value = mock_client

        tool = DeleteSearchAlertTool()
        result = tool({"id": 999}, {})

        assert result.isError
        assert "404" in result.content[0].text


class TestSubscribeToDocketAlertToolCall:
    @patch.object(SubscribeToDocketAlertTool, "get_client")
    def test_success(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.docket_alerts.subscribe.return_value = {
            "id": 10,
            "docket": 123,
            "alert_type": 1,
        }
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_get_client.return_value = mock_client

        tool = SubscribeToDocketAlertTool()
        result = tool({"docket": 123}, {})

        assert not result.isError
        data = json.loads(result.content[0].text)
        assert data["docket"] == 123
        assert data["alert_type"] == 1

    @patch.object(SubscribeToDocketAlertTool, "get_client")
    def test_api_error(self, mock_get_client):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_client.docket_alerts.subscribe.side_effect = (
            CourtListenerAPIError(
                status_code=400, detail="Bad request", response=mock_response
            )
        )
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_get_client.return_value = mock_client

        tool = SubscribeToDocketAlertTool()
        result = tool({"docket": 123}, {})

        assert result.isError


class TestUnsubscribeFromDocketAlertToolCall:
    @patch.object(UnsubscribeFromDocketAlertTool, "get_client")
    def test_success(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.docket_alerts.unsubscribe.return_value = None
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_get_client.return_value = mock_client

        tool = UnsubscribeFromDocketAlertTool()
        result = tool({"docket": 123}, {})

        assert not result.isError
        assert "123" in result.content[0].text

    @patch.object(UnsubscribeFromDocketAlertTool, "get_client")
    def test_not_found(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.docket_alerts.unsubscribe.side_effect = ValueError(
            "No docket alert found for docket 999"
        )
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_get_client.return_value = mock_client

        tool = UnsubscribeFromDocketAlertTool()
        result = tool({"docket": 999}, {})

        assert result.isError
        assert "999" in result.content[0].text

    @patch.object(UnsubscribeFromDocketAlertTool, "get_client")
    def test_api_error(self, mock_get_client):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_client.docket_alerts.unsubscribe.side_effect = (
            CourtListenerAPIError(
                status_code=500,
                detail="Server error",
                response=mock_response,
            )
        )
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_get_client.return_value = mock_client

        tool = UnsubscribeFromDocketAlertTool()
        result = tool({"docket": 123}, {})

        assert result.isError


# ---------------------------------------------------------------------------
# Integration tests (hit the real API)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCreateSearchAlertToolIntegration:
    def test_create_and_verify(self, client):
        tool = CreateSearchAlertTool()
        with patch.object(
            CreateSearchAlertTool, "get_client", return_value=client
        ):
            result = tool(
                {"name": "MCP Tool Test", "query": "q=test", "rate": "off"},
                {},
            )
        assert not result.isError
        data = json.loads(result.content[0].text)
        assert data["name"] == "MCP Tool Test"
        assert "id" in data
        client.alerts.delete(data["id"])


@pytest.mark.integration
class TestDeleteSearchAlertToolIntegration:
    def test_delete(self, client):
        alert = client.alerts.create(
            name="MCP Delete Test", query="q=test", rate="off"
        )
        tool = DeleteSearchAlertTool()
        with patch.object(
            DeleteSearchAlertTool, "get_client", return_value=client
        ):
            result = tool({"id": alert["id"]}, {})
        assert not result.isError


@pytest.mark.integration
class TestSubscribeToDocketAlertToolIntegration:
    DOCKET_ID = 68571705

    def test_subscribe(self, client):
        tool = SubscribeToDocketAlertTool()
        with patch.object(
            SubscribeToDocketAlertTool, "get_client", return_value=client
        ):
            result = tool({"docket": self.DOCKET_ID}, {})
        assert not result.isError
        data = json.loads(result.content[0].text)
        assert data["alert_type"] == 1
        assert "id" in data
        client.docket_alerts.delete(data["id"])


@pytest.mark.integration
class TestUnsubscribeFromDocketAlertToolIntegration:
    DOCKET_ID = 68571705

    def test_unsubscribe(self, client):
        client.docket_alerts.subscribe(docket=self.DOCKET_ID)
        tool = UnsubscribeFromDocketAlertTool()
        with patch.object(
            UnsubscribeFromDocketAlertTool,
            "get_client",
            return_value=client,
        ):
            result = tool({"docket": self.DOCKET_ID}, {})
        assert not result.isError

    def test_unsubscribe_not_found(self, client):
        tool = UnsubscribeFromDocketAlertTool()
        with patch.object(
            UnsubscribeFromDocketAlertTool,
            "get_client",
            return_value=client,
        ):
            result = tool({"docket": 0}, {})
        assert result.isError
        assert "No docket alert found" in result.content[0].text
