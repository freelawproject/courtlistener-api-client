"""Tests for SearchAlerts and DocketAlerts helpers."""

from unittest.mock import MagicMock

import pytest

from courtlistener.alerts import DocketAlerts, SearchAlerts


# ---------------------------------------------------------------------------
# Unit tests (no API calls, no integration marker)
# ---------------------------------------------------------------------------


class TestSearchAlertsValidation:
    def test_invalid_rate_raises(self):
        mock_client = MagicMock()
        alerts = SearchAlerts(mock_client)
        with pytest.raises(ValueError, match="Invalid rate"):
            alerts.create(
                name="test", query="q=test", rate="invalid"
            )

    def test_invalid_alert_type_raises(self):
        mock_client = MagicMock()
        alerts = SearchAlerts(mock_client)
        with pytest.raises(ValueError, match="Invalid alert_type"):
            alerts.create(
                name="test",
                query="q=test",
                rate="dly",
                alert_type="z",
            )

    def test_update_invalid_rate_raises(self):
        mock_client = MagicMock()
        alerts = SearchAlerts(mock_client)
        with pytest.raises(ValueError, match="Invalid rate"):
            alerts.update(1, rate="bad")

    def test_update_invalid_alert_type_raises(self):
        mock_client = MagicMock()
        alerts = SearchAlerts(mock_client)
        with pytest.raises(ValueError, match="Invalid alert_type"):
            alerts.update(1, alert_type="z")


class TestDocketAlertsValidation:
    def test_docket_alert_invalid_alert_type_raises(self):
        mock_client = MagicMock()
        da = DocketAlerts(mock_client)
        with pytest.raises(ValueError, match="Invalid alert_type"):
            da.create(docket=1, alert_type=99)

    def test_update_invalid_alert_type_raises(self):
        mock_client = MagicMock()
        da = DocketAlerts(mock_client)
        with pytest.raises(ValueError, match="Invalid alert_type"):
            da.update(1, alert_type=99)


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
            updated = client.alerts.update(
                alert["id"], name="SDK Updated"
            )
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
            alert = client.docket_alerts.create(
                docket=self.DOCKET_ID
            )
            assert isinstance(alert, dict)
            assert alert["alert_type"] == 1
            assert "id" in alert
        finally:
            if alert and "id" in alert:
                client.docket_alerts.delete(alert["id"])

    def test_subscribe(self, client):
        alert = None
        try:
            alert = client.docket_alerts.subscribe(
                docket=self.DOCKET_ID
            )
            assert isinstance(alert, dict)
            assert alert["alert_type"] == 1
        finally:
            if alert and "id" in alert:
                client.docket_alerts.delete(alert["id"])

    def test_unsubscribe(self, client):
        alert = client.docket_alerts.create(
            docket=self.DOCKET_ID
        )
        client.docket_alerts.unsubscribe(alert["id"])

    def test_update_docket_alert(self, client):
        alert = None
        try:
            alert = client.docket_alerts.create(
                docket=self.DOCKET_ID
            )
            updated = client.docket_alerts.update(
                alert["id"], alert_type=0
            )
            assert updated["alert_type"] == 0
        finally:
            if alert and "id" in alert:
                client.docket_alerts.delete(alert["id"])

    def test_delete_docket_alert(self, client):
        alert = client.docket_alerts.create(
            docket=self.DOCKET_ID
        )
        client.docket_alerts.delete(alert["id"])

    def test_list_docket_alerts(self, client):
        alert = None
        try:
            alert = client.docket_alerts.create(
                docket=self.DOCKET_ID
            )
            results = client.docket_alerts.list()
            assert len(results.results) >= 1
        finally:
            if alert and "id" in alert:
                client.docket_alerts.delete(alert["id"])
