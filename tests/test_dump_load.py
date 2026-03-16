"""Tests for ResourceIterator dump/load and index tracking."""

from unittest.mock import MagicMock

from courtlistener.models.page import Page
from courtlistener.resource import ResourceIterator


def make_page(results, next_url=None, previous_url=None, count=10):
    """Create a Page with the given results and pagination URLs."""
    return Page(
        count=count,
        next=next_url,
        previous=previous_url,
        results=results,
    )


def make_iterator(pages):
    """Create a ResourceIterator with pre-loaded pages.

    Pages is a list of (results, next_url) tuples. The iterator is set up
    so that calling next() cycles through the pages via _fetch_page mock.
    """
    client = MagicMock()
    resource = MagicMock()
    resource._client = client
    resource._endpoint = "/api/rest/v4/test/"

    first_page = pages[0]
    remaining_pages = list(pages[1:])

    def fetch_side_effect(url=None):
        if remaining_pages:
            return remaining_pages.pop(0)
        raise ValueError("No more pages")

    iterator = ResourceIterator(resource, {"type": "test"})
    iterator._current_page = first_page
    iterator._fetch_page = fetch_side_effect
    return iterator, client


class TestDump:
    def test_dump_returns_expected_keys(self):
        page = make_page([{"id": 1}, {"id": 2}])
        it, _ = make_iterator([page])
        dumped = it.dump()
        assert set(dumped.keys()) == {
            "current_page",
            "filters",
            "endpoint",
            "index",
            "count",
        }

    def test_dump_captures_current_page(self):
        page = make_page([{"id": 1}])
        it, _ = make_iterator([page])
        dumped = it.dump()
        assert dumped["current_page"]["results"] == [{"id": 1}]

    def test_dump_captures_filters_and_endpoint(self):
        page = make_page([{"id": 1}])
        it, _ = make_iterator([page])
        dumped = it.dump()
        assert dumped["filters"] == {"type": "test"}
        assert dumped["endpoint"] == "/api/rest/v4/test/"

    def test_dump_captures_index(self):
        page = make_page([{"id": 1}, {"id": 2}, {"id": 3}])
        it, _ = make_iterator([page])
        # Iterate through 2 items
        items = []
        for item in it:
            items.append(item)
            if len(items) == 2:
                break
        dumped = it.dump()
        assert dumped["index"] == 2

    def test_dump_captures_cached_count(self):
        page = make_page([{"id": 1}], count=42)
        it, _ = make_iterator([page])
        _ = it.count  # trigger count resolution
        dumped = it.dump()
        assert dumped["count"] == 42

    def test_dump_count_none_when_not_resolved(self):
        page = make_page([{"id": 1}], count="http://example.com/count")
        it, _ = make_iterator([page])
        dumped = it.dump()
        assert dumped["count"] is None


class TestLoad:
    def test_load_restores_current_page(self):
        page = make_page([{"id": 1}, {"id": 2}])
        it, client = make_iterator([page])
        dumped = it.dump()
        restored = ResourceIterator.load(client, dumped)
        assert restored.results == [{"id": 1}, {"id": 2}]

    def test_load_restores_index(self):
        page = make_page([{"id": 1}, {"id": 2}, {"id": 3}])
        it, client = make_iterator([page])
        items = []
        for item in it:
            items.append(item)
            if len(items) == 2:
                break
        dumped = it.dump()
        restored = ResourceIterator.load(client, dumped)
        assert restored._index == 2

    def test_load_restores_cached_count(self):
        page = make_page([{"id": 1}], count=99)
        it, client = make_iterator([page])
        _ = it.count
        dumped = it.dump()
        restored = ResourceIterator.load(client, dumped)
        assert restored.count == 99

    def test_load_restores_filters_and_endpoint(self):
        page = make_page([{"id": 1}])
        it, client = make_iterator([page])
        dumped = it.dump()
        restored = ResourceIterator.load(client, dumped)
        assert restored._filters == {"type": "test"}
        assert restored._endpoint == "/api/rest/v4/test/"


class TestIterationIndex:
    def test_index_starts_at_zero(self):
        page = make_page([{"id": 1}])
        it, _ = make_iterator([page])
        assert it._index == 0

    def test_index_increments_during_iteration(self):
        page = make_page([{"id": 1}, {"id": 2}, {"id": 3}])
        it, _ = make_iterator([page])
        items = list(it)
        assert it._index == 3
        assert len(items) == 3

    def test_resume_iteration_mid_page(self):
        """After dump/load, iteration resumes from where it left off."""
        page = make_page(
            [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}, {"id": 5}]
        )
        it, client = make_iterator([page])

        # Iterate through first 3
        items = []
        for item in it:
            items.append(item)
            if len(items) == 3:
                break
        assert [i["id"] for i in items] == [1, 2, 3]

        # Dump and reload
        dumped = it.dump()
        restored = ResourceIterator.load(client, dumped)

        # Continue iteration — should get items 4 and 5
        remaining = list(restored)
        assert [i["id"] for i in remaining] == [4, 5]

    def test_resume_from_index_zero(self):
        """Loading with index=0 yields all results."""
        page = make_page([{"id": 1}, {"id": 2}])
        it, client = make_iterator([page])
        dumped = it.dump()
        assert dumped["index"] == 0

        restored = ResourceIterator.load(client, dumped)
        items = list(restored)
        assert [i["id"] for i in items] == [1, 2]

    def test_resume_at_end_of_page(self):
        """Loading after all items consumed yields nothing."""
        page = make_page([{"id": 1}, {"id": 2}])
        it, client = make_iterator([page])
        list(it)  # exhaust
        dumped = it.dump()
        assert dumped["index"] == 2

        restored = ResourceIterator.load(client, dumped)
        remaining = list(restored)
        assert remaining == []


class TestRoundTrip:
    def test_dump_load_roundtrip_preserves_state(self):
        page = make_page([{"id": 1}, {"id": 2}], count=50)
        it, client = make_iterator([page])
        _ = it.count
        next(iter(it))  # consume one item

        dumped = it.dump()
        restored = ResourceIterator.load(client, dumped)

        assert restored._index == 1
        assert restored._count == 50
        assert restored._filters == {"type": "test"}
        assert restored._endpoint == "/api/rest/v4/test/"
        assert restored.results == [{"id": 1}, {"id": 2}]
