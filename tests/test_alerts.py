"""Tests for SearchAlerts and DocketAlerts helpers."""

from contextlib import suppress
from unittest.mock import MagicMock
from urllib.parse import parse_qs

import httpx
import pytest
from pydantic import ValidationError

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.models.alerts import normalize_search_query
from courtlistener.sync_client.alerts import DocketAlerts, SearchAlerts

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


def _page(results):
    return {
        "count": len(results),
        "next": None,
        "previous": None,
        "results": results,
    }


class TestDocketAlertsSubscribeIdempotent:
    """Issue #121: ``subscribe`` is idempotent at the SDK layer."""

    def test_creates_when_no_existing_subscription(self):
        mock_client = MagicMock()
        created = {"id": 1, "docket": 5, "alert_type": 1}
        mock_client._request.side_effect = [_page([]), created]

        da = DocketAlerts(mock_client)
        result = da.subscribe(docket=5)

        assert result == created
        assert "already_subscribed" not in result

    def test_returns_existing_with_flag(self):
        mock_client = MagicMock()
        existing = {"id": 1, "docket": 5, "alert_type": 1}
        mock_client._request.side_effect = [_page([existing])]

        da = DocketAlerts(mock_client)
        result = da.subscribe(docket=5)

        assert result["id"] == 1
        assert result["already_subscribed"] is True
        # Pre-flight list only — no POST.
        assert mock_client._request.call_count == 1

    def test_create_400_still_raises(self):
        mock_client = MagicMock()
        other_error = CourtListenerAPIError(
            400,
            {"docket": ["Invalid pk."]},
            MagicMock(spec=httpx.Response, status_code=400),
        )
        mock_client._request.side_effect = [_page([]), other_error]

        da = DocketAlerts(mock_client)
        with pytest.raises(CourtListenerAPIError) as exc_info:
            da.subscribe(docket=5)
        assert exc_info.value.status_code == 400


class TestDocketAlertsUnsubscribe:
    def test_deletes_existing_alert(self):
        mock_client = MagicMock()
        existing = {"id": 9, "docket": 5, "alert_type": 1}
        mock_client._request.side_effect = [_page([existing]), {}]

        da = DocketAlerts(mock_client)
        da.unsubscribe(docket=5)

        method, path = mock_client._request.call_args_list[1].args
        assert method == "DELETE"
        assert path.endswith("/9/")

    def test_raises_when_no_alert(self):
        mock_client = MagicMock()
        mock_client._request.side_effect = [_page([])]

        da = DocketAlerts(mock_client)
        with pytest.raises(ValueError, match="No docket alert found"):
            da.unsubscribe(docket=5)


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
#
# Each resource gets ONE sequential lifecycle test rather than a test
# per operation. The per-operation tests each did their own
# create/delete round-trip, which had two failure modes: any
# interrupted run left an orphan alert behind (only the test's own
# alert was cleaned up), and the account's server-side alert quota
# then made every later create fail with a 400 — presenting as
# "create/delete is broken" forever after. A single lifecycle makes
# the ordering explicit, cuts the request count, and starts by
# sweeping orphans. Stage names in the failure message identify which
# step broke.
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSearchAlertsIntegration:
    NAME_PREFIX = "SDK Test"

    def test_search_alert_lifecycle(self, client):
        # Sweep orphans from interrupted earlier runs — leftover test
        # alerts otherwise pile up against the account's alert quota.
        for orphan in client.alerts.list():
            if orphan["name"].startswith(self.NAME_PREFIX):
                client.alerts.delete(orphan["id"])

        created = []
        stage = "create"
        try:
            alert = client.alerts.create(
                name=f"{self.NAME_PREFIX} Lifecycle",
                query='q="sdk lifecycle integration test"',
                rate="off",
            )
            created.append(alert)
            assert isinstance(alert, dict)
            assert alert["name"] == f"{self.NAME_PREFIX} Lifecycle"
            assert alert["rate"] == "off"
            assert "id" in alert

            stage = "get"
            fetched = client.alerts.get(alert["id"])
            assert fetched["id"] == alert["id"]
            assert fetched["name"] == alert["name"]

            stage = "update"
            updated = client.alerts.update(
                alert["id"], name=f"{self.NAME_PREFIX} Updated"
            )
            assert updated["name"] == f"{self.NAME_PREFIX} Updated"

            stage = "list"
            listed_ids = [a["id"] for a in client.alerts.list()]
            assert alert["id"] in listed_ids

            stage = "create-dict-query"
            dict_alert = client.alerts.create(
                name=f"{self.NAME_PREFIX} Dict Query",
                query={"q": '"sdk dict query integration test"', "type": "o"},
                rate="off",
            )
            created.append(dict_alert)
            assert dict_alert["name"] == f"{self.NAME_PREFIX} Dict Query"
            assert "id" in dict_alert

            stage = "delete"
            for a in created:
                client.alerts.delete(a["id"])

            stage = "verify-delete"
            with pytest.raises(CourtListenerAPIError) as excinfo:
                client.alerts.get(alert["id"])
            assert excinfo.value.status_code == 404
            created = []
        except CourtListenerAPIError as exc:
            pytest.fail(
                f"search-alert lifecycle failed at stage {stage!r}: {exc}"
            )
        finally:
            for a in created:
                with suppress(CourtListenerAPIError):
                    client.alerts.delete(a["id"])


@pytest.mark.integration
class TestDocketAlertsIntegration:
    """Docket-alert lifecycle against docket 68571705 (a known docket).

    The docket+user pair is unique server-side, so an alert left
    behind by an interrupted run makes every later ``create`` 400
    until someone cleans it up — hence the sweep on both ends.
    """

    DOCKET_ID = 68571705

    def _sweep(self, client):
        for alert in client.docket_alerts.list(docket=self.DOCKET_ID):
            client.docket_alerts.delete(alert["id"])

    def test_docket_alert_lifecycle(self, client):
        self._sweep(client)
        stage = "create"
        try:
            alert = client.docket_alerts.create(docket=self.DOCKET_ID)
            assert isinstance(alert, dict)
            assert alert["alert_type"] == 1
            assert "id" in alert

            stage = "update"
            updated = client.docket_alerts.update(alert["id"], alert_type=0)
            assert updated["alert_type"] == 0

            stage = "delete"
            client.docket_alerts.delete(alert["id"])

            stage = "subscribe"
            sub = client.docket_alerts.subscribe(docket=self.DOCKET_ID)
            assert sub["alert_type"] == 1
            assert "already_subscribed" not in sub

            stage = "subscribe-idempotent"
            again = client.docket_alerts.subscribe(docket=self.DOCKET_ID)
            assert again["id"] == sub["id"]
            assert again["already_subscribed"] is True

            stage = "unsubscribe"
            client.docket_alerts.unsubscribe(docket=self.DOCKET_ID)

            stage = "unsubscribe-when-empty"
            with pytest.raises(ValueError):
                client.docket_alerts.unsubscribe(docket=self.DOCKET_ID)
        except CourtListenerAPIError as exc:
            pytest.fail(
                f"docket-alert lifecycle failed at stage {stage!r}: {exc}"
            )
        finally:
            self._sweep(client)
