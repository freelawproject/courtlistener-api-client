"""Unit tests for AsyncApiUsage."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from courtlistener.async_client.api_usage import AsyncApiUsage

pytestmark = pytest.mark.asyncio

PAYLOAD = {
    "current_usage": [
        {
            "scope": "user",
            "rate": "5000/hour",
            "used": 12,
            "limit": 5000,
            "remaining": 4988,
            "window_seconds": 3600,
            "reset_at": "2026-09-14T18:00:00+00:00",
            "blocked": False,
        }
    ],
    "historical_usage": {"2026-09-14": 12, "total": 12},
    "membership": None,
}


def _mock_client(*responses):
    client = MagicMock()
    client._request = AsyncMock(side_effect=list(responses) or None)
    return client


class TestApiUsage:
    async def test_get_fetches_usage(self):
        client = _mock_client(PAYLOAD)
        usage = AsyncApiUsage(client)
        result = await usage.get()

        method, path = client._request.await_args.args
        assert method == "GET"
        assert path.endswith("/api-usage/")
        assert client._request.await_args.kwargs == {}
        assert result == PAYLOAD
