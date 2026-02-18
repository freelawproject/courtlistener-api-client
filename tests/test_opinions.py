"""Hand-written tests for Opinion and Cluster endpoints."""

import pytest


@pytest.mark.integration
class TestOpinions:

    def test_list(self, client):
        """Opinions list returns results."""
        results = client.opinions.list()
        assert isinstance(results.results, list)
        assert len(results.results) > 0

    def test_get_by_id(self, client):
        """Get a single opinion and verify structure."""
        results = client.opinions.list()
        assert results.results, "Need at least one opinion"

        opinion_id = results.results[0]["id"]
        opinion = client.opinions.get(opinion_id)

        assert isinstance(opinion, dict)
        assert opinion["id"] == opinion_id
        assert "type" in opinion
        assert "cluster" in opinion


@pytest.mark.integration
class TestClusters:

    def test_list(self, client):
        """Clusters list returns results."""
        results = client.clusters.list()
        assert isinstance(results.results, list)
        assert len(results.results) > 0

    def test_get_by_id(self, client):
        """Get a single cluster and verify structure."""
        results = client.clusters.list()
        assert results.results, "Need at least one cluster"

        cluster_id = results.results[0]["id"]
        cluster = client.clusters.get(cluster_id)

        assert isinstance(cluster, dict)
        assert cluster["id"] == cluster_id
        assert "case_name" in cluster
