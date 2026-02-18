"""Hand-written tests for Opinion and Cluster endpoints.

Each test validates the actual response data structure and content.
"""

import pytest


@pytest.mark.integration
class TestOpinions:

    def test_list(self, client):
        """Opinions list returns results with expected fields."""
        results = client.opinions.list()
        assert len(results.results) > 0
        for opinion in results.results:
            assert "id" in opinion
            assert "type" in opinion
            assert "cluster" in opinion

    def test_get_by_id(self, client):
        """Get a single opinion and verify it matches the list."""
        results = client.opinions.list()
        first = results.results[0]

        opinion = client.opinions.get(first["id"])

        assert opinion["id"] == first["id"]
        assert opinion["type"] == first["type"]
        assert opinion["cluster"] == first["cluster"]
        assert "date_created" in opinion
        assert "download_url" in opinion


@pytest.mark.integration
class TestClusters:

    def test_list(self, client):
        """Clusters list returns results with expected fields."""
        results = client.clusters.list()
        assert len(results.results) > 0
        for cluster in results.results:
            assert "id" in cluster
            assert "case_name" in cluster
            assert "docket" in cluster
            assert "date_filed" in cluster

    def test_get_by_id(self, client):
        """Get a single cluster and verify it matches the list."""
        results = client.clusters.list()
        first = results.results[0]

        cluster = client.clusters.get(first["id"])

        assert cluster["id"] == first["id"]
        assert cluster["case_name"] == first["case_name"]
        assert cluster["docket"] == first["docket"]
        assert "sub_opinions" in cluster
        assert "citations" in cluster
