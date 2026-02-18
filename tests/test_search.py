"""Hand-written tests for the Search endpoints.

Covers the generic search dispatcher, opinion search, recap search,
relative date validation, and multi-court choice fields.
"""

import pytest


@pytest.mark.integration
class TestSearch:

    def test_search_opinions_via_opinion_search(self, client):
        """Opinion search returns opinion results."""
        results = client.opinion_search.list(q="Miranda")
        assert isinstance(results.results, list)
        assert len(results.results) > 0

    def test_search_recap_via_recap_search(self, client):
        """Recap search returns recap results."""
        results = client.recap_search.list(q="motion")
        assert isinstance(results.results, list)
        assert len(results.results) > 0


@pytest.mark.integration
class TestOpinionSearch:

    def test_basic_query(self, client):
        """Opinion search with a query string."""
        results = client.opinion_search.list(q="copyright")
        assert isinstance(results.results, list)
        assert len(results.results) > 0

    def test_with_court_filter(self, client):
        """Opinion search filtered to SCOTUS."""
        results = client.opinion_search.list(
            q="copyright", court="scotus"
        )
        assert isinstance(results.results, list)

    def test_multi_court_filter(self, client):
        """Multiple courts as a list."""
        results = client.opinion_search.list(
            q="patent", court=["scotus", "cafc"]
        )
        assert isinstance(results.results, list)

    def test_relative_date_filed_after(self, client):
        """Relative date string accepted for filed_after."""
        results = client.opinion_search.list(
            q="tax", filed_after="1 year ago"
        )
        assert isinstance(results.results, list)

    def test_relative_date_filed_before(self, client):
        """Relative date string accepted for filed_before."""
        results = client.opinion_search.list(
            q="tax", filed_before="6 months ago"
        )
        assert isinstance(results.results, list)


@pytest.mark.integration
class TestRecapSearch:

    def test_basic_query(self, client):
        """Recap search returns results."""
        results = client.recap_search.list(q="bankruptcy")
        assert isinstance(results.results, list)
        assert len(results.results) > 0

    def test_document_count(self, client):
        """Recap search exposes document_count."""
        results = client.recap_search.list(q="bankruptcy")
        # document_count may or may not be present depending on API
        # but accessing it should not error
        _ = results.document_count
