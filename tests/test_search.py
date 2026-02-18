"""Hand-written tests for the Search endpoints.

Covers opinion search, recap search, relative date validation, and
multi-court choice fields. Each test validates the actual response
data to catch cases where the API silently ignores bad query params.
"""

from datetime import date, timedelta

import pytest


@pytest.mark.integration
class TestSearch:

    def test_search_opinions_via_opinion_search(self, client):
        """Opinion search returns opinion results."""
        results = client.opinion_search.list(q="Miranda")
        assert len(results.results) > 0

    def test_search_recap_via_recap_search(self, client):
        """Recap search returns recap results."""
        results = client.recap_search.list(q="motion")
        assert len(results.results) > 0


@pytest.mark.integration
class TestOpinionSearch:

    def test_basic_query(self, client):
        """Opinion search with a query string."""
        results = client.opinion_search.list(q="copyright")
        assert len(results.results) > 0

    def test_with_court_filter(self, client):
        """Opinion search filtered to SCOTUS returns only SCOTUS."""
        results = client.opinion_search.list(
            q="copyright", court="scotus"
        )
        assert len(results.results) > 0
        for result in results.results:
            assert result["court_id"] == "scotus"

    def test_multi_court_filter(self, client):
        """Multiple courts as a list — results from those courts."""
        results = client.opinion_search.list(
            q="patent", court=["scotus", "cafc"]
        )
        assert len(results.results) > 0
        for result in results.results:
            assert result["court_id"] in ("scotus", "cafc")

    def test_relative_date_filed_after(self, client):
        """Relative date string filters results correctly."""
        results = client.opinion_search.list(
            q="tax", filed_after="1 year ago"
        )
        assert len(results.results) > 0
        one_year_ago = date.today() - timedelta(days=365)
        for result in results.results:
            filed = date.fromisoformat(result["dateFiled"])
            assert filed >= one_year_ago

    def test_relative_date_filed_before(self, client):
        """Relative date string accepted for filed_before."""
        results = client.opinion_search.list(
            q="tax", filed_before="6 months ago"
        )
        assert len(results.results) > 0
        six_months_ago = date.today() - timedelta(days=180)
        for result in results.results:
            filed = date.fromisoformat(result["dateFiled"])
            assert filed <= six_months_ago


@pytest.mark.integration
class TestRecapSearch:

    def test_basic_query(self, client):
        """Recap search returns results."""
        results = client.recap_search.list(q="bankruptcy")
        assert len(results.results) > 0

    def test_document_count(self, client):
        """Recap search exposes document_count."""
        results = client.recap_search.list(q="bankruptcy")
        # document_count may or may not be present depending on API
        # but accessing it should not error
        _ = results.document_count
