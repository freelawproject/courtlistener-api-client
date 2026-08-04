"""Unit tests for AsyncSearchAlerts and AsyncDocketAlerts."""

from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs

import httpx
import pytest
from pydantic import ValidationError

from courtlistener.async_client.alerts import (
    AsyncDocketAlerts,
    AsyncSearchAlerts,
)
from courtlistener.exceptions import CourtListenerAPIError

pytestmark = pytest.mark.asyncio


def _mock_client(*responses):
    client = MagicMock()
    client._request = AsyncMock(side_effect=list(responses) or None)
    return client


def _page(results):
    return {
        "count": len(results),
        "next": None,
        "previous": None,
        "results": results,
    }


class TestSearchAlerts:
    async def test_create_posts_normalized_query(self):
        client = _mock_client({"id": 1})
        alerts = AsyncSearchAlerts(client)
        await alerts.create(name="test", query={"q": "test"}, rate="dly")
        body = client._request.await_args.kwargs["json"]
        assert parse_qs(body["query"])["q"] == ["test"]
        assert body["rate"] == "dly"

    async def test_update_with_none_passes_through(self):
        client = _mock_client({"id": 1})
        alerts = AsyncSearchAlerts(client)
        await alerts.update(1, name="new name")

    async def test_update_with_dict_query(self):
        client = _mock_client({"id": 1, "query": "q=test"})
        alerts = AsyncSearchAlerts(client)
        await alerts.update(1, query={"q": "test"})
        body = client._request.await_args.kwargs["json"]
        assert parse_qs(body["query"])["q"] == ["test"]

    async def test_invalid_rate_raises(self):
        alerts = AsyncSearchAlerts(_mock_client())
        with pytest.raises(ValidationError):
            await alerts.create(name="test", query="q=test", rate="invalid")

    async def test_update_rejects_unknown_fields(self):
        alerts = AsyncSearchAlerts(_mock_client())
        with pytest.raises(ValidationError):
            await alerts.update(1, unknown_field="value")

    async def test_delete(self):
        client = _mock_client({})
        alerts = AsyncSearchAlerts(client)
        await alerts.delete(3)
        method, path = client._request.await_args.args
        assert method == "DELETE"
        assert path.endswith("/3/")


class TestDocketAlertsSubscribeIdempotent:
    async def test_creates_when_no_existing_subscription(self):
        created = {"id": 1, "docket": 5, "alert_type": 1}
        client = _mock_client(_page([]), created)

        da = AsyncDocketAlerts(client)
        result = await da.subscribe(docket=5)

        assert result == created
        assert "already_subscribed" not in result

    async def test_returns_existing_with_flag(self):
        existing = {"id": 1, "docket": 5, "alert_type": 1}
        client = _mock_client(_page([existing]))

        da = AsyncDocketAlerts(client)
        result = await da.subscribe(docket=5)

        assert result["id"] == 1
        assert result["already_subscribed"] is True
        # Pre-flight list only — no POST.
        assert client._request.await_count == 1

    async def test_create_400_still_raises(self):
        other_error = CourtListenerAPIError(
            400,
            {"docket": ["Invalid pk."]},
            MagicMock(spec=httpx.Response, status_code=400),
        )
        client = _mock_client(_page([]), other_error)

        da = AsyncDocketAlerts(client)
        with pytest.raises(CourtListenerAPIError) as exc_info:
            await da.subscribe(docket=5)
        assert exc_info.value.status_code == 400


class TestDocketAlertsUnsubscribe:
    async def test_deletes_existing_alert(self):
        existing = {"id": 9, "docket": 5, "alert_type": 1}
        client = _mock_client(_page([existing]), {})

        da = AsyncDocketAlerts(client)
        await da.unsubscribe(docket=5)

        method, path = client._request.await_args_list[1].args
        assert method == "DELETE"
        assert path.endswith("/9/")

    async def test_raises_when_no_alert(self):
        client = _mock_client(_page([]))
        da = AsyncDocketAlerts(client)
        with pytest.raises(ValueError, match="No docket alert found"):
            await da.unsubscribe(docket=5)


class TestDocketAlertsValidation:
    async def test_invalid_alert_type_raises(self):
        da = AsyncDocketAlerts(_mock_client())
        with pytest.raises(ValidationError):
            await da.create(docket=1, alert_type=99)

    async def test_update_rejects_unknown_fields(self):
        da = AsyncDocketAlerts(_mock_client())
        with pytest.raises(ValidationError):
            await da.update(1, unknown_field="value")
