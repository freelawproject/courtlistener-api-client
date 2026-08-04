"""Unit tests for the AsyncCitationLookup helper."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from courtlistener.async_client.citation_lookup import (
    MAX_TEXT_LENGTH,
    AsyncCitationLookup,
)
from courtlistener.exceptions import CourtListenerAPIError

pytestmark = pytest.mark.asyncio


def _mock_client(*responses):
    client = MagicMock()
    client._request = AsyncMock(side_effect=list(responses) or None)
    return client


def _throttle_error(wait_seconds=1):
    wait_until = datetime.now(timezone.utc) + timedelta(seconds=wait_seconds)
    return CourtListenerAPIError(
        429,
        {"wait_until": wait_until.isoformat()},
        MagicMock(spec=httpx.Response, status_code=429),
    )


class TestLookupText:
    async def test_raises_on_oversized_text(self):
        lookup = AsyncCitationLookup(_mock_client())
        with pytest.raises(ValueError, match="exceeds the maximum"):
            await lookup.lookup_text("x" * (MAX_TEXT_LENGTH + 1))

    async def test_429_raises_without_retry_flag(self):
        client = _mock_client(_throttle_error())
        lookup = AsyncCitationLookup(client)
        with pytest.raises(CourtListenerAPIError):
            await lookup.lookup_text("576 U.S. 644")
        assert client._request.await_count == 1

    async def test_retry_on_rate_limit_sleeps_and_retries(self):
        results = [{"citation": "576 U.S. 644", "status": 200}]
        client = _mock_client(_throttle_error(), results)
        lookup = AsyncCitationLookup(client)

        with patch(
            "courtlistener.async_client.citation_lookup.asyncio.sleep",
            new_callable=AsyncMock,
        ) as mock_sleep:
            output = await lookup.lookup_text(
                "576 U.S. 644", retry_on_rate_limit=True
            )

        assert output == results
        assert client._request.await_count == 2
        mock_sleep.assert_awaited_once()

    async def test_second_429_raises(self):
        client = _mock_client(_throttle_error(), _throttle_error())
        lookup = AsyncCitationLookup(client)
        with (
            patch(
                "courtlistener.async_client.citation_lookup.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            pytest.raises(CourtListenerAPIError),
        ):
            await lookup.lookup_text("576 U.S. 644", retry_on_rate_limit=True)


class TestLookupCitation:
    async def test_posts_citation_parts(self):
        client = _mock_client([{"citation": "576 U.S. 644", "status": 200}])
        lookup = AsyncCitationLookup(client)
        await lookup.lookup_citation(576, "U.S.", "644")
        kwargs = client._request.await_args.kwargs
        assert kwargs["data"] == {
            "volume": "576",
            "reporter": "U.S.",
            "page": "644",
        }


class TestLookupTextBatched:
    async def test_no_throttle_single_call(self):
        lookup = AsyncCitationLookup(_mock_client())
        results = [
            {
                "citation": "576 U.S. 644",
                "status": 200,
                "start_index": 0,
                "end_index": 12,
            }
        ]

        with patch.object(
            lookup, "lookup_text", AsyncMock(return_value=results)
        ):
            output = await lookup.lookup_text_batched("576 U.S. 644")

        assert len(output) == 1
        assert output[0]["status"] == 200

    async def test_resubmits_on_throttle(self):
        lookup = AsyncCitationLookup(_mock_client())
        text = "First 388 U.S. 1 then 576 U.S. 644"

        first_call_results = [
            {
                "citation": "388 U.S. 1",
                "status": 200,
                "start_index": 6,
                "end_index": 16,
            },
            {
                "citation": "576 U.S. 644",
                "status": 429,
                "start_index": 22,
                "end_index": 34,
            },
        ]
        second_call_results = [
            {
                "citation": "576 U.S. 644",
                "status": 200,
                "start_index": 0,
                "end_index": 12,
            },
        ]

        with patch.object(
            lookup,
            "lookup_text",
            AsyncMock(side_effect=[first_call_results, second_call_results]),
        ):
            output = await lookup.lookup_text_batched(text)

        assert len(output) == 2
        assert output[0]["status"] == 200
        assert output[0]["start_index"] == 6
        assert output[1]["status"] == 200
        # Second result's index should be adjusted to original text
        assert output[1]["start_index"] == 22
