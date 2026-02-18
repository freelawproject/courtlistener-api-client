"""Hand-written tests for the Dockets endpoint.

Exercises the most complex filter pipelines: date filters, in-filters
with choice validation, string filters, and related fields.

Each test validates the actual response data to catch cases where the
API silently ignores bad query params.
"""

from datetime import date

import pytest


@pytest.mark.integration
class TestDocketsList:
    def test_list_with_court_filter(self, client):
        """Filter by court using the short code."""
        results = client.dockets.list(court="scotus")
        assert len(results.results) > 0
        for docket in results.results:
            assert docket["court"].endswith("/courts/scotus/")

    def test_list_with_date_filter(self, client):
        """Nested date filter dict gets flattened to query params."""
        results = client.dockets.list(date_filed={"gte": "2020-01-01"})
        assert len(results.results) > 0
        for docket in results.results:
            filed = date.fromisoformat(docket["date_filed"])
            assert filed >= date(2020, 1, 1)

    def test_list_with_source_in_filter(self, client):
        """In-filter pipeline: list of ints → source__in=0,1."""
        results = client.dockets.list(source=[0, 1])
        assert isinstance(results.results, list)
        for docket in results.results:
            assert docket["source"] in (0, 1)

    def test_list_with_source_display_name(self, client):
        """Source choice by display name resolves to int value."""
        results = client.dockets.list(source="RECAP")
        assert len(results.results) > 0
        for docket in results.results:
            assert docket["source"] == 1  # RECAP = 1

    def test_list_with_nature_of_suit_filter(self, client):
        """String filter with 'contains' lookup."""
        results = client.dockets.list(nature_of_suit={"contains": "Contract"})
        assert isinstance(results.results, list)
        for docket in results.results:
            assert "Contract" in docket["nature_of_suit"]

    def test_list_with_date_range(self, client):
        """Date filter with both gte and lte."""
        results = client.dockets.list(
            date_filed={
                "gte": "2023-01-01",
                "lte": "2023-12-31",
            }
        )
        assert len(results.results) > 0
        for docket in results.results:
            filed = date.fromisoformat(docket["date_filed"])
            assert date(2023, 1, 1) <= filed <= date(2023, 12, 31)


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
