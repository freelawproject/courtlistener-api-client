"""Tests for pagination behavior: integration plus deprecation shims."""

import warnings
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from courtlistener import CourtListener


@contextmanager
def warnings_as_errors():
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        yield


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


def _iterator(pages):
    cl = CourtListener(api_token="tok")
    cl._request = MagicMock(side_effect=pages)
    return cl.courts.list()


def _page(results, count=None):
    return {
        "count": count if count is not None else len(results),
        "next": None,
        "previous": None,
        "results": results,
    }


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
