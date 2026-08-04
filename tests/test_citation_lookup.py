"""Tests for the CitationLookup helper."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.sync_client.citation_lookup import (
    MAX_TEXT_LENGTH,
    CitationLookup,
    _split_text,
)


def _mock_client(*responses):
    client = MagicMock()
    client._request = MagicMock(side_effect=list(responses) or None)
    return client


def _throttle_error(wait_seconds=1):
    wait_until = datetime.now(timezone.utc) + timedelta(seconds=wait_seconds)
    return CourtListenerAPIError(
        429,
        {"wait_until": wait_until.isoformat()},
        MagicMock(spec=httpx.Response, status_code=429),
    )


class TestRateLimitRetry:
    """Mirrors TestLookupText in tests/test_async_citation_lookup.py."""

    def test_raises_on_oversized_text(self):
        lookup = CitationLookup(_mock_client())
        with pytest.raises(ValueError, match="exceeds the maximum"):
            lookup.lookup_text("x" * (MAX_TEXT_LENGTH + 1))

    def test_429_raises_without_retry_flag(self):
        client = _mock_client(_throttle_error())
        lookup = CitationLookup(client)
        with pytest.raises(CourtListenerAPIError):
            lookup.lookup_text("576 U.S. 644")
        assert client._request.call_count == 1

    def test_retry_on_rate_limit_sleeps_and_retries(self):
        results = [{"citation": "576 U.S. 644", "status": 200}]
        client = _mock_client(_throttle_error(), results)
        lookup = CitationLookup(client)

        with patch(
            "courtlistener.sync_client.citation_lookup.time.sleep"
        ) as mock_sleep:
            output = lookup.lookup_text(
                "576 U.S. 644", retry_on_rate_limit=True
            )

        assert output == results
        assert client._request.call_count == 2
        mock_sleep.assert_called_once()

    def test_second_429_raises(self):
        client = _mock_client(_throttle_error(), _throttle_error())
        lookup = CitationLookup(client)
        with (
            patch("courtlistener.sync_client.citation_lookup.time.sleep"),
            pytest.raises(CourtListenerAPIError),
        ):
            lookup.lookup_text("576 U.S. 644", retry_on_rate_limit=True)


@pytest.mark.integration
class TestLookupText:
    def test_single_known_citation(self, client):
        """A well-known citation returns status 200 with clusters."""
        results = client.citation_lookup.lookup_text(
            "Obergefell v. Hodges, 576 U.S. 644 (2015)"
        )
        assert len(results) >= 1
        match = results[0]
        assert match["status"] == 200
        assert match["citation"] == "576 U.S. 644"
        assert len(match["clusters"]) >= 1
        assert match["start_index"] >= 0
        assert match["end_index"] > match["start_index"]

    def test_multiple_citations(self, client):
        """Multiple citations are returned in text order."""
        text = (
            "See Obergefell v. Hodges, 576 U.S. 644 (2015), and "
            "Loving v. Virginia, 388 U.S. 1 (1967)."
        )
        results = client.citation_lookup.lookup_text(text)
        assert len(results) >= 2
        # Results should be ordered by position in text
        assert results[0]["start_index"] < results[1]["start_index"]

    def test_not_found_citation(self, client):
        """A valid-looking but nonexistent citation returns status 404."""
        results = client.citation_lookup.lookup_text("999 U.S. 9999")
        assert len(results) >= 1
        assert results[0]["status"] == 404

    def test_no_citations_in_text(self, client):
        """Regular text with no citations returns an empty list."""
        results = client.citation_lookup.lookup_text(
            "The quick brown fox jumps over the lazy dog."
        )
        assert results == []


@pytest.mark.integration
class TestLookupCitation:
    def test_direct_lookup(self, client):
        """Direct volume/reporter/page lookup returns a match."""
        results = client.citation_lookup.lookup_citation(576, "U.S.", "644")
        assert len(results) >= 1
        assert results[0]["status"] == 200
        assert len(results[0]["clusters"]) >= 1


class TestTextTooLong:
    def test_raises_on_oversized_text(self):
        """Text exceeding 64,000 chars raises ValueError client-side."""
        lookup = CitationLookup.__new__(CitationLookup)
        with pytest.raises(ValueError, match="64000"):
            lookup.lookup_text("x" * 64_001)


class TestSplitText:
    def test_short_text_single_chunk(self):
        """Text under the limit is returned as a single chunk."""
        chunks = _split_text("hello world")
        assert chunks == [(0, "hello world")]

    def test_splits_at_whitespace(self):
        """Long text is split at whitespace boundaries."""
        # Create text with known whitespace positions
        word = "a" * 100
        text = " ".join([word] * 700)  # ~70,700 chars
        chunks = _split_text(text)
        assert len(chunks) >= 2
        # Each chunk should be within the limit
        for _offset, chunk in chunks:
            assert len(chunk) <= 64_000
        # Reassembling chunks should reproduce the original text
        reassembled = "".join(chunk for _, chunk in chunks)
        assert reassembled == text

    def test_offsets_are_correct(self):
        """Chunk offsets correctly map back to the original text."""
        word = "a" * 100
        text = " ".join([word] * 700)
        chunks = _split_text(text)
        for offset, chunk in chunks:
            assert text[offset : offset + len(chunk)] == chunk


class TestLookupTextBatched:
    def test_no_throttle_single_call(self):
        """When no results are throttled, only one call is made."""
        mock_client = MagicMock()
        lookup = CitationLookup(mock_client)

        results = [
            {
                "citation": "576 U.S. 644",
                "status": 200,
                "start_index": 0,
                "end_index": 12,
            }
        ]

        with patch.object(lookup, "lookup_text", return_value=results):
            output = lookup.lookup_text_batched("576 U.S. 644")

        assert len(output) == 1
        assert output[0]["status"] == 200

    def test_resubmits_on_throttle(self):
        """Throttled citations trigger a follow-up request."""
        mock_client = MagicMock()
        lookup = CitationLookup(mock_client)

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
            side_effect=[first_call_results, second_call_results],
        ):
            output = lookup.lookup_text_batched(text)

        assert len(output) == 2
        assert output[0]["status"] == 200
        assert output[0]["start_index"] == 6
        assert output[1]["status"] == 200
        # Second result's index should be adjusted to original text
        assert output[1]["start_index"] == 22
