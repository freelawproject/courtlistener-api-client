"""Hand-written tests for the Dockets endpoint.

Exercises the most complex filter pipelines: date filters, in-filters
with choice validation, string filters, and related fields.
"""

import pytest


@pytest.mark.integration
class TestDocketsList:

    def test_list_with_court_filter(self, client):
        """Filter by court using the short code."""
        results = client.dockets.list(court="scotus")
        assert isinstance(results.results, list)
        assert len(results.results) > 0

    def test_list_with_date_filter(self, client):
        """Nested date filter dict gets flattened to query params."""
        results = client.dockets.list(
            date_filed={"gte": "2020-01-01"}
        )
        assert isinstance(results.results, list)
        assert len(results.results) > 0

    def test_list_with_source_in_filter(self, client):
        """In-filter pipeline: list of ints → source__in=0,1."""
        results = client.dockets.list(source=[0, 1])
        assert isinstance(results.results, list)

    def test_list_with_source_display_name(self, client):
        """Source choice by display name resolves to int value."""
        results = client.dockets.list(source="RECAP")
        assert isinstance(results.results, list)

    def test_list_with_nature_of_suit_filter(self, client):
        """String filter with 'contains' lookup."""
        results = client.dockets.list(
            nature_of_suit={"contains": "Contract"}
        )
        assert isinstance(results.results, list)


@pytest.mark.integration
class TestDocketsGet:

    def test_get_by_id(self, client):
        """Get a specific docket and verify response structure."""
        results = client.dockets.list()
        assert results.results, "Need at least one docket"

        docket_id = results.results[0]["id"]
        docket = client.dockets.get(docket_id)

        assert isinstance(docket, dict)
        assert docket["id"] == docket_id
        assert "court" in docket
        assert "date_created" in docket
