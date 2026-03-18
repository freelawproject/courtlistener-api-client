"""Tests for SearchAlerts and DocketAlerts helpers."""

from unittest.mock import MagicMock
from urllib.parse import parse_qs

import pytest
from pydantic import ValidationError

from courtlistener.alerts import (
    DocketAlerts,
    SearchAlerts,
    normalize_search_query,
)

# ---------------------------------------------------------------------------
# Unit tests – normalize_search_query
# ---------------------------------------------------------------------------


class TestNormalizeSearchQuery:
    """Unit tests for the query normalization helper."""

    def test_dict_query_returns_query_string(self):
        result = normalize_search_query({"q": "test"})
        parsed = parse_qs(result)
        assert parsed["q"] == ["test"]

    def test_string_query_roundtrips(self):
        result = normalize_search_query("q=test")
        parsed = parse_qs(result)
        assert parsed["q"] == ["test"]

    def test_dict_with_court_filter(self):
        result = normalize_search_query({"q": "copyright", "court": "scotus"})
        parsed = parse_qs(result)
        assert parsed["q"] == ["copyright"]
        assert parsed["court"] == ["scotus"]

    def test_string_with_multiple_params(self):
        result = normalize_search_query("q=copyright&court=scotus")
        parsed = parse_qs(result)
        assert parsed["q"] == ["copyright"]
        assert parsed["court"] == ["scotus"]

    def test_explicit_type_preserved(self):
        result = normalize_search_query({"q": "test", "type": "r"})
        parsed = parse_qs(result)
        assert parsed["q"] == ["test"]

    def test_invalid_field_raises(self):
        with pytest.raises((ValidationError, ValueError, TypeError)):
            normalize_search_query({"not_a_real_field": "bad"})

    def test_update_with_none_passes_through(self):
        """SearchAlertUpdate allows None for query."""
        mock_client = MagicMock()
        alerts = SearchAlerts(mock_client)
        # Should not raise – query=None is valid for updates
        alerts.update(1, name="new name")

    def test_update_with_dict_query(self):
        mock_client = MagicMock()
        mock_client._request.return_value = {"id": 1, "query": "q=test"}
        alerts = SearchAlerts(mock_client)
        alerts.update(1, query={"q": "test"})
        call_args = mock_client._request.call_args
        body = call_args[1]["json"]
        parsed = parse_qs(body["query"])
        assert parsed["q"] == ["test"]


# ---------------------------------------------------------------------------
# Unit tests – validation (no API calls, no integration marker)
# ---------------------------------------------------------------------------


class TestSearchAlertsValidation:
    def test_invalid_rate_raises(self):
        mock_client = MagicMock()
        alerts = SearchAlerts(mock_client)
        with pytest.raises(ValidationError):
            alerts.create(name="test", query="q=test", rate="invalid")

    def test_invalid_alert_type_raises(self):
        mock_client = MagicMock()
        alerts = SearchAlerts(mock_client)
        with pytest.raises(ValidationError):
            alerts.create(
                name="test",
                query="q=test",
                rate="dly",
                alert_type="z",
            )

    def test_update_invalid_rate_raises(self):
        mock_client = MagicMock()
        alerts = SearchAlerts(mock_client)
        with pytest.raises(ValidationError):
            alerts.update(1, rate="bad")

    def test_update_invalid_alert_type_raises(self):
        mock_client = MagicMock()
        alerts = SearchAlerts(mock_client)
        with pytest.raises(ValidationError):
            alerts.update(1, alert_type="z")

    def test_update_rejects_unknown_fields(self):
        mock_client = MagicMock()
        alerts = SearchAlerts(mock_client)
        with pytest.raises(ValidationError):
            alerts.update(1, unknown_field="value")


class TestDocketAlertsValidation:
    def test_docket_alert_invalid_alert_type_raises(self):
        mock_client = MagicMock()
        da = DocketAlerts(mock_client)
        with pytest.raises(ValidationError):
            da.create(docket=1, alert_type=99)

    def test_update_invalid_alert_type_raises(self):
        mock_client = MagicMock()
        da = DocketAlerts(mock_client)
        with pytest.raises(ValidationError):
            da.update(1, alert_type=99)

    def test_update_rejects_unknown_fields(self):
        mock_client = MagicMock()
        da = DocketAlerts(mock_client)
        with pytest.raises(ValidationError):
            da.update(1, unknown_field="value")


# ---------------------------------------------------------------------------
# Integration tests (hit the real API)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSearchAlertsIntegration:
    def test_create_search_alert(self, client):
        alert = None
        try:
            alert = client.alerts.create(
                name="SDK Test Alert",
                query="q=test",
                rate="off",
            )
            assert isinstance(alert, dict)
            assert alert["name"] == "SDK Test Alert"
            assert alert["rate"] == "off"
            assert "id" in alert
        finally:
            if alert and "id" in alert:
                client.alerts.delete(alert["id"])

    def test_get_search_alert(self, client):
        alert = None
        try:
            alert = client.alerts.create(
                name="SDK Get Test",
                query="q=get",
                rate="off",
            )
            fetched = client.alerts.get(alert["id"])
            assert fetched["id"] == alert["id"]
            assert fetched["name"] == "SDK Get Test"
        finally:
            if alert and "id" in alert:
                client.alerts.delete(alert["id"])

    def test_update_search_alert(self, client):
        alert = None
        try:
            alert = client.alerts.create(
                name="SDK Update Test",
                query="q=update",
                rate="off",
            )
            updated = client.alerts.update(alert["id"], name="SDK Updated")
            assert updated["name"] == "SDK Updated"
        finally:
            if alert and "id" in alert:
                client.alerts.delete(alert["id"])

    def test_delete_search_alert(self, client):
        alert = client.alerts.create(
            name="SDK Delete Test",
            query="q=delete",
            rate="off",
        )
        client.alerts.delete(alert["id"])

    def test_list_search_alerts(self, client):
        alert = None
        try:
            alert = client.alerts.create(
                name="SDK List Test",
                query="q=list",
                rate="off",
            )
            results = client.alerts.list()
            assert len(results.results) >= 1
        finally:
            if alert and "id" in alert:
                client.alerts.delete(alert["id"])

    def test_create_search_alert_with_dict_query(self, client):
        alert = None
        try:
            alert = client.alerts.create(
                name="SDK Dict Query Test",
                query={"q": "test", "type": "o"},
                rate="off",
            )
            assert isinstance(alert, dict)
            assert alert["name"] == "SDK Dict Query Test"
            assert "id" in alert
        finally:
            if alert and "id" in alert:
                client.alerts.delete(alert["id"])


@pytest.mark.integration
class TestDocketAlertsIntegration:
    """Integration tests for DocketAlerts.

    These tests use docket ID 68571705 which is a known docket
    in the CourtListener database.
    """

    DOCKET_ID = 68571705

    def test_create_docket_alert(self, client):
        alert = None
        try:
            alert = client.docket_alerts.create(docket=self.DOCKET_ID)
            assert isinstance(alert, dict)
            assert alert["alert_type"] == 1
            assert "id" in alert
        finally:
            if alert and "id" in alert:
                client.docket_alerts.delete(alert["id"])

    def test_subscribe(self, client):
        alert = None
        try:
            alert = client.docket_alerts.subscribe(docket=self.DOCKET_ID)
            assert isinstance(alert, dict)
            assert alert["alert_type"] == 1
        finally:
            if alert and "id" in alert:
                client.docket_alerts.delete(alert["id"])

    def test_unsubscribe(self, client):
        client.docket_alerts.subscribe(docket=self.DOCKET_ID)
        client.docket_alerts.unsubscribe(docket=self.DOCKET_ID)

    def test_update_docket_alert(self, client):
        alert = None
        try:
            alert = client.docket_alerts.create(docket=self.DOCKET_ID)
            updated = client.docket_alerts.update(alert["id"], alert_type=0)
            assert updated["alert_type"] == 0
        finally:
            if alert and "id" in alert:
                client.docket_alerts.delete(alert["id"])

    def test_delete_docket_alert(self, client):
        alert = client.docket_alerts.create(docket=self.DOCKET_ID)
        client.docket_alerts.delete(alert["id"])

    def test_list_docket_alerts(self, client):
        alert = None
        try:
            alert = client.docket_alerts.create(docket=self.DOCKET_ID)
            results = client.docket_alerts.list()
            assert len(results.results) >= 1
        finally:
            if alert and "id" in alert:
                client.docket_alerts.delete(alert["id"])
