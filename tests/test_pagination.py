"""Hand-written tests for pagination behavior on a real endpoint."""

import pytest


@pytest.mark.integration
class TestPagination:

    def test_first_page_has_results(self, client):
        """Courts endpoint returns a first page with results."""
        results = client.courts.list()
        assert len(results.results) > 0

    def test_has_next(self, client):
        """Endpoints with multiple pages should have a next page."""
        results = client.courts.list()
        assert results.has_next()

    def test_next_page(self, client):
        """Calling next() fetches a different page of results."""
        results = client.courts.list()
        first_page_ids = [r["id"] for r in results.results]

        results.next()
        second_page_ids = [r["id"] for r in results.results]

        assert second_page_ids != first_page_ids

    def test_count(self, client):
        """Count returns a positive integer."""
        results = client.courts.list()
        count = results.count
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
