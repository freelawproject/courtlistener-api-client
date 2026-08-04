"""Tests for pagination behavior: unit, integration, deprecation shims.

The unit classes mirror tests/test_async_pagination.py one-for-one; keep
the two in step so a generated sync client stays covered.
"""

import warnings
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from courtlistener import CourtListener
from courtlistener.sync_client.resource import ResourceIterator

NEXT_URL = "https://www.courtlistener.com/api/rest/v4/courts/?cursor=abc"


@contextmanager
def warnings_as_errors():
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        yield


def _page(results, next=None, previous=None, count=None):
    return {
        "count": count if count is not None else len(results),
        "next": next,
        "previous": previous,
        "results": results,
    }


def _iterator(pages) -> ResourceIterator:
    cl = CourtListener(api_token="tok")
    cl._request = MagicMock(side_effect=pages)
    return cl.courts.list()


@pytest.mark.integration
class TestPagination:
    def test_first_page_has_results(self, client):
        """Courts endpoint returns a first page with results."""
        results = client.courts.list()
        assert len(results.get_results()) > 0

    def test_has_next(self, client):
        """Endpoints with multiple pages should have a next page."""
        results = client.courts.list()
        assert results.has_next()

    def test_next_page(self, client):
        """Calling next() fetches a different page of results."""
        results = client.courts.list()
        first_page_ids = [r["id"] for r in results.get_results()]

        results.next()
        second_page_ids = [r["id"] for r in results.get_results()]

        assert second_page_ids != first_page_ids

    def test_count(self, client):
        """Count returns a positive integer."""
        results = client.courts.list()
        count = results.get_count()
        assert isinstance(count, int)
        assert count > 0

    def test_iteration_yields_items(self, client):
        """Iterating through results yields dicts across pages."""
        results = client.courts.list()
        items = []
        for item in results:
            items.append(item)
            if len(items) >= 25:
                break

        assert len(items) == 25
        assert all(isinstance(item, dict) for item in items)

    def test_previous_raises_on_first_page(self, client):
        """Calling previous() on the first page raises ValueError."""
        results = client.courts.list()
        assert not results.has_previous()

        with pytest.raises(ValueError, match="No previous page"):
            results.previous()


class TestCurrentPage:
    def test_fetches_first_page(self):
        it = _iterator([_page([{"id": "scotus"}])])
        page = it.get_current_page()
        assert page.results == [{"id": "scotus"}]

    def test_page_is_cached(self):
        it = _iterator([_page([{"id": "scotus"}])])
        first = it.get_current_page()
        second = it.get_current_page()
        assert first is second
        assert it._client._request.call_count == 1

    def test_results_shortcut(self):
        it = _iterator([_page([{"id": "scotus"}])])
        assert it.get_results() == [{"id": "scotus"}]


class TestNavigation:
    def test_has_next(self):
        it = _iterator([_page([{"id": 1}], next=NEXT_URL)])
        assert it.has_next()

    def test_no_next(self):
        it = _iterator([_page([{"id": 1}])])
        assert not it.has_next()

    def test_next_fetches_next_url(self):
        it = _iterator(
            [
                _page([{"id": 1}], next=NEXT_URL),
                _page([{"id": 2}], previous="prev"),
            ]
        )
        it.next()
        assert it.get_results() == [{"id": 2}]
        method, path = it._client._request.call_args_list[1].args
        assert method == "GET"
        assert path == "/api/rest/v4/courts/?cursor=abc"

    def test_next_raises_without_next_page(self):
        it = _iterator([_page([{"id": 1}])])
        with pytest.raises(ValueError, match="No next page"):
            it.next()

    def test_previous_raises_on_first_page(self):
        it = _iterator([_page([{"id": 1}])])
        assert not it.has_previous()
        with pytest.raises(ValueError, match="No previous page"):
            it.previous()


class TestIteration:
    def test_iterates_across_pages(self):
        it = _iterator(
            [
                _page([{"id": 1}, {"id": 2}], next=NEXT_URL),
                _page([{"id": 3}]),
            ]
        )
        items = list(it)
        assert [item["id"] for item in items] == [1, 2, 3]

    def test_iteration_respects_result_index(self):
        it = _iterator([_page([{"id": 1}, {"id": 2}, {"id": 3}])])
        collected = []
        for item in it:
            collected.append(item)
            if len(collected) == 2:
                break
        assert [item["id"] for item in it] == [3]


class TestCount:
    def test_integer_count(self):
        it = _iterator([_page([{"id": 1}], count=42)])
        assert it.get_count() == 42

    def test_count_url_is_fetched(self):
        count_url = (
            "https://www.courtlistener.com/api/rest/v4/courts/?count=on"
        )
        it = _iterator(
            [
                _page([{"id": 1}], count=count_url),
                {"count": 99},
            ]
        )
        assert it.get_count() == 99
        method, path = it._client._request.call_args_list[1].args
        assert path == "/api/rest/v4/courts/?count=on"

    def test_count_is_cached(self):
        it = _iterator([_page([{"id": 1}], count=42)])
        it.get_count()
        it.get_count()
        assert it._client._request.call_count == 1

    def test_missing_count_raises(self):
        it = _iterator([_page([{"id": 1}], count=-1) | {"count": None}])
        with pytest.raises(ValueError, match="No count URL"):
            it.get_count()


class TestDumpLoad:
    def test_round_trip_uses_cached_page(self):
        it = _iterator([_page([{"id": 1}], count=7)])
        it.get_count()
        state = it.dump()

        restored_client = CourtListener(api_token="tok")
        restored_client._request = MagicMock()
        restored = ResourceIterator.load(restored_client, state)

        assert restored.get_results() == [{"id": 1}]
        assert restored.get_count() == 7
        restored_client._request.assert_not_called()

    def test_dump_preserves_position(self):
        it = _iterator([_page([{"id": 1}, {"id": 2}])])
        collected = []
        for item in it:
            collected.append(item)
            if len(collected) == 1:
                break
        state = it.dump()
        assert state["page_result_index"] == 1


class TestDeprecatedProperties:
    """The property accessors are backwards-compat shims for the
    ``get_*`` methods and warn on use."""

    @pytest.mark.parametrize(
        "prop,method",
        [
            ("current_page", "get_current_page"),
            ("count", "get_count"),
            ("document_count", "get_document_count"),
            ("results", "get_results"),
        ],
    )
    def test_property_warns_and_matches_method(self, prop, method):
        it = _iterator([_page([{"id": 1}], count=7)])
        with pytest.warns(DeprecationWarning, match=f"use {method}\\(\\)"):
            via_property = getattr(it, prop)
        assert via_property == getattr(it, method)()

    def test_methods_do_not_warn(self):
        it = _iterator([_page([{"id": 1}], count=7)])
        with warnings_as_errors():
            assert it.get_results() == [{"id": 1}]
            assert it.get_count() == 7
            assert it.get_current_page().results == [{"id": 1}]
            assert it.get_document_count() is None

    def test_iteration_does_not_warn(self):
        """Internal code paths use the methods, not the shims."""
        it = _iterator([_page([{"id": 1}, {"id": 2}])])
        with warnings_as_errors():
            assert [item["id"] for item in it] == [1, 2]

    def test_dump_does_not_warn(self):
        it = _iterator([_page([{"id": 1}])])
        with warnings_as_errors():
            state = it.dump()
        assert state["page_result_index"] == 0
