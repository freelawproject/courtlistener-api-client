"""Parametrized tests that hit every endpoint in the ENDPOINTS registry.

For each endpoint, we verify:
1. `.list()` returns a ResourceIterator with a valid results list
2. `.get(id)` on the first result returns a dict (where applicable)

Some endpoints are special-cased:
- Search sub-endpoints (opinion_search, recap_search, etc.) share the
  /search/ path and need a `type` param (handled by their Literal default).
- Some endpoints may return empty results — that's fine, we just verify
  the call doesn't error.
- Some endpoints are write-only or require specific params — these are
  skipped for the generic get test.
"""

import pytest

from courtlistener.models import ENDPOINTS
from courtlistener.resource import ResourceIterator

# Endpoints that don't support GET list (POST-only, write-only, or
# require special parameters).
SKIP_LIST = {
    "search",
    "increment_event",
    "recap_fetch",
    "recap_query",
    "disclosure_typeahead",
}

#  Search-type endpoints where .get(id) doesn't make sense.
SKIP_GET = SKIP_LIST | {
    "opinion_search",
    "recap_search",
    "recap_docket_search",
    "recap_document_search",
    "judge_search",
    "oral_argument_search",
}


@pytest.mark.integration
class TestEndpointList:
    """Verify .list() works for every registered endpoint."""

    @pytest.mark.parametrize(
        "endpoint_name",
        [
            name
            for name in ENDPOINTS
            if name not in SKIP_LIST
        ],
        ids=[
            name
            for name in ENDPOINTS
            if name not in SKIP_LIST
        ],
    )
    def test_list(self, client, endpoint_name):
        resource = getattr(client, endpoint_name)
        results = resource.list()

        assert isinstance(results, ResourceIterator)
        assert isinstance(results.results, list)


@pytest.mark.integration
class TestEndpointGet:
    """Verify .get(id) works for endpoints that support it."""

    @pytest.mark.parametrize(
        "endpoint_name",
        [
            name
            for name in ENDPOINTS
            if name not in SKIP_GET
        ],
        ids=[
            name
            for name in ENDPOINTS
            if name not in SKIP_GET
        ],
    )
    def test_get(self, client, endpoint_name):
        resource = getattr(client, endpoint_name)
        results = resource.list()

        if not results.results:
            pytest.skip(
                f"No results for {endpoint_name}, can't test .get()"
            )

        first = results.results[0]
        item_id = first.get("id")
        if item_id is None:
            pytest.skip(
                f"First result for {endpoint_name} has no 'id' field"
            )

        detail = resource.get(item_id)
        assert isinstance(detail, dict)
        assert detail.get("id") == item_id
