from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from courtlistener.exceptions import CourtListenerAPIError

if TYPE_CHECKING:
    from courtlistener.client import CourtListener

MAX_TEXT_LENGTH = 64_000
THROTTLE_STATUS = 429
MAX_RETRY_WAIT_SECONDS = 90.0


class CitationLookup:
    """Helper for the citation lookup and verification API.

    This endpoint extracts citations from text using eyecite and verifies
    them against CourtListener's database.

    See: https://www.courtlistener.com/help/api/rest/citation-lookup/
    """

    ENDPOINT = "/citation-lookup/"

    def __init__(self, client: CourtListener) -> None:
        self._client = client

    def lookup_text(
        self,
        text: str,
        *,
        retry_on_rate_limit: bool = False,
    ) -> list[dict[str, Any]]:
        """Look up all citations in a block of text.

        Sends text to CourtListener's citation-lookup endpoint, which
        uses eyecite to extract citations and matches them against the
        database.

        Args:
            text: Legal text containing citations (max 64,000 chars).
            retry_on_rate_limit: If True, a whole-request 429 response
                triggers a single retry after sleeping until the
                ``wait_until`` timestamp in the error body (capped at
                ``MAX_RETRY_WAIT_SECONDS``). If the second attempt also
                429s, the error is raised.

        Returns:
            List of citation results. Each result contains:
            - citation: The citation string found
            - normalized_citations: Canonical forms of the citation
            - start_index/end_index: Position in the input text
            - status: 200 (found), 404 (not found), 400 (invalid),
              300 (ambiguous), 429 (throttled)
            - error_message: Details if lookup failed
            - clusters: Matched CourtListener cluster objects

        Raises:
            ValueError: If text exceeds 64,000 characters.
            CourtListenerAPIError: On API errors (including 429 when
                retry is disabled or the retry also fails).
        """
        if len(text) > MAX_TEXT_LENGTH:
            raise ValueError(
                f"Text length {len(text)} exceeds the maximum of "
                f"{MAX_TEXT_LENGTH} characters."
            )
        try:
            result = self._client._request(
                "POST", self.ENDPOINT, data={"text": text}
            )
        except CourtListenerAPIError as e:
            if not retry_on_rate_limit or e.status_code != THROTTLE_STATUS:
                raise
            wait = _wait_until_seconds(e.detail)
            if wait is None:
                raise
            time.sleep(wait)
            result = self._client._request(
                "POST", self.ENDPOINT, data={"text": text}
            )
        assert isinstance(result, list)
        return result

    def lookup_citation(
        self, volume: int, reporter: str, page: str
    ) -> list[dict[str, Any]]:
        """Look up a specific citation by volume/reporter/page.

        Args:
            volume: Volume number (e.g., 576).
            reporter: Reporter abbreviation (e.g., "U.S.", "F.3d").
            page: Page number or string (e.g., "644").

        Returns:
            List of citation results with matched cluster objects.
        """
        result = self._client._request(
            "POST",
            self.ENDPOINT,
            data={
                "volume": str(volume),
                "reporter": reporter,
                "page": page,
            },
        )
        assert isinstance(result, list)
        return result

    def lookup_text_batched(self, text: str) -> list[dict[str, Any]]:
        """Look up citations with automatic handling for large texts.

        Handles texts that exceed either the 64,000 character limit or
        the 250 citation-per-request throttle. Texts longer than 64,000
        characters are split at whitespace boundaries. When the API
        throttles citations beyond the 250th (status 429), the
        remaining text is re-submitted automatically.

        Args:
            text: Legal text of any length.

        Returns:
            Combined list of all citation results across batches.
        """
        all_results: list[dict[str, Any]] = []

        for chunk_offset, chunk in _split_text(text):
            chunk_results = self._lookup_chunk(chunk, chunk_offset)
            all_results.extend(chunk_results)

        return all_results

    def _lookup_chunk(
        self, chunk: str, base_offset: int
    ) -> list[dict[str, Any]]:
        """Look up citations in a single chunk, re-submitting on 429s.

        Args:
            chunk: Text chunk within the 64,000 char limit.
            base_offset: Character offset of this chunk in the
                original text, used to adjust start/end indices.

        Returns:
            Citation results with indices adjusted to the original text.
        """
        all_results: list[dict[str, Any]] = []
        remaining = chunk
        running_offset = 0

        while remaining:
            results = self.lookup_text(remaining)
            throttled: list[dict[str, Any]] = []
            resolved: list[dict[str, Any]] = []

            for r in results:
                if r["status"] == THROTTLE_STATUS:
                    throttled.append(r)
                else:
                    resolved.append(r)

            # Adjust indices to account for chunk and sub-chunk offsets
            total_offset = base_offset + running_offset
            if total_offset > 0:
                for r in resolved:
                    r["start_index"] += total_offset
                    r["end_index"] += total_offset

            all_results.extend(resolved)

            if not throttled:
                break

            # Re-submit from the start of the first throttled citation
            first_throttled_start = throttled[0]["start_index"]
            running_offset += first_throttled_start
            remaining = remaining[first_throttled_start:]

        return all_results


def parse_wait_until(detail: Any) -> datetime | None:
    """Parse the ``wait_until`` timestamp from a 429 error body.

    Returns a timezone-aware datetime, or None if the body shape is
    unexpected or the value can't be parsed. Naive timestamps are
    interpreted as UTC.
    """
    if not isinstance(detail, dict):
        return None
    wait_until = detail.get("wait_until")
    if not isinstance(wait_until, str):
        return None
    try:
        target = datetime.fromisoformat(wait_until)
    except ValueError:
        return None
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    return target


def _wait_until_seconds(detail: Any) -> float | None:
    """Seconds to sleep before retrying a 429, clamped to the cap, or None."""
    target = parse_wait_until(detail)
    if target is None:
        return None
    seconds = (target - datetime.now(timezone.utc)).total_seconds()
    return max(0.0, min(seconds, MAX_RETRY_WAIT_SECONDS))


def _split_text(text: str) -> list[tuple[int, str]]:
    """Split text into chunks of at most MAX_TEXT_LENGTH characters.

    Splits at whitespace boundaries when possible.

    Args:
        text: The text to split.

    Returns:
        List of (offset, chunk) tuples.
    """
    if len(text) <= MAX_TEXT_LENGTH:
        return [(0, text)]

    chunks: list[tuple[int, str]] = []
    offset = 0

    while offset < len(text):
        end = offset + MAX_TEXT_LENGTH

        if end >= len(text):
            chunks.append((offset, text[offset:]))
            break

        # Find last whitespace before the limit
        split_at = text.rfind(" ", offset, end)
        if split_at <= offset:
            # No whitespace found; split at the hard limit
            split_at = end

        chunks.append((offset, text[offset:split_at]))
        offset = split_at

    return chunks
