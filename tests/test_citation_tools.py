"""Tests for the citation MCP tools."""

from unittest.mock import MagicMock, patch

from courtlistener.mcp.session import InMemorySessionStore
from courtlistener.mcp.tools.analyze_citations_tool import AnalyzeCitationsTool
from courtlistener.mcp.tools.citation_utils import (
    canonical_key,
    format_resolved_citations,
)
from courtlistener.mcp.tools.extract_citations_tool import ExtractCitationsTool
from courtlistener.mcp.tools.resume_citation_analysis_tool import (
    ResumeCitationAnalysisTool,
)

SAMPLE_TEXT = (
    "The Court held in Obergefell v. Hodges, 576 U.S. 644 (2015), "
    "that same-sex couples have a fundamental right. See also "
    "Loving v. Virginia, 388 U.S. 1 (1967). In id. at 12, the "
    "Court noted the history. The statute at 42 U.S.C. § 1983 "
    "provides a cause of action."
)


class TestExtractCitationsTool:
    def setup_method(self):
        self.tool = ExtractCitationsTool()

    def test_resolved_output(self):
        session = InMemorySessionStore()
        result = self.tool({"text": SAMPLE_TEXT}, session)
        text = result.content[0].text
        assert "576 U.S. 644" in text
        assert "388 U.S. 1" in text
        assert "42 U.S.C. § 1983" in text
        assert "unique case(s)" in text

    def test_flat_output(self):
        session = InMemorySessionStore()
        result = self.tool({"text": SAMPLE_TEXT, "resolve": False}, session)
        text = result.content[0].text
        assert "[full]" in text
        assert "576 U.S. 644" in text

    def test_no_citations(self):
        session = InMemorySessionStore()
        result = self.tool({"text": "No legal citations here."}, session)
        assert "No citations found" in result.content[0].text

    def test_stateless(self):
        """extract_citations should not modify session."""
        session = InMemorySessionStore()
        self.tool({"text": SAMPLE_TEXT}, session)
        # Use _data directly for a comprehensive check covering both
        # queries and citation_analyses (stronger than a single get_query call).
        assert session._data == {}


class TestAnalyzeCitationsTool:
    def setup_method(self):
        self.tool = AnalyzeCitationsTool()

    def test_stores_in_session(self):
        """analyze_citations should store results in session."""
        session = InMemorySessionStore()
        mock_client = MagicMock()
        mock_client.citation_lookup.lookup_text.return_value = [
            {
                "citation": "576 U.S. 644",
                "status": 200,
                "start_index": 0,
                "end_index": 12,
                "clusters": [
                    {
                        "id": 1,
                        "case_name": "Obergefell v. Hodges",
                        "date_filed": "2015-06-26",
                        "citation_count": 942,
                        "absolute_url": "/opinion/1/test/",
                        "citations": [],
                    }
                ],
            },
            {
                "citation": "388 U.S. 1",
                "status": 200,
                "start_index": 14,
                "end_index": 24,
                "clusters": [
                    {
                        "id": 2,
                        "case_name": "Loving v. Virginia",
                        "date_filed": "1967-06-12",
                        "citation_count": 1523,
                        "absolute_url": "/opinion/2/test/",
                        "citations": [],
                    }
                ],
            },
        ]

        with (
            patch.object(session, "make_id", return_value="abcd1234"),
            patch.object(self.tool, "get_client") as mock_get_client,
        ):
            mock_get_client.return_value.__enter__ = lambda s: mock_client
            mock_get_client.return_value.__exit__ = MagicMock(
                return_value=False
            )
            result = self.tool({"text": SAMPLE_TEXT}, session)

        text = result.content[0].text
        assert "Job ID: abcd1234" in text

        # get_user_id() returns "local" in test context (no ContextVar)
        job = session.get_citation_analysis("local", "abcd1234")
        assert job is not None
        assert "576 U.S. 644" in job["verified"]
        assert "388 U.S. 1" in job["verified"]
        assert len(job["pending"]) == 0

    def test_output_contains_case_details(self):
        """Verified cases should show name, date, and URL."""
        session = InMemorySessionStore()
        mock_client = MagicMock()
        mock_client.citation_lookup.lookup_text.return_value = [
            {
                "citation": "576 U.S. 644",
                "status": 200,
                "start_index": 0,
                "end_index": 12,
                "clusters": [
                    {
                        "id": 1,
                        "case_name": "Obergefell v. Hodges",
                        "date_filed": "2015-06-26",
                        "citation_count": 942,
                        "absolute_url": "/opinion/1/obergefell/",
                        "citations": [],
                    }
                ],
            },
        ]

        with patch.object(self.tool, "get_client") as mock_get_client:
            mock_get_client.return_value.__enter__ = lambda s: mock_client
            mock_get_client.return_value.__exit__ = MagicMock(
                return_value=False
            )
            result = self.tool({"text": "576 U.S. 644"}, session)

        text = result.content[0].text
        assert "Obergefell v. Hodges" in text
        assert "2015-06-26" in text
        assert "942" in text
        assert "courtlistener.com" in text

    def test_not_found_citation(self):
        """Citations not in CourtListener should show NOT FOUND."""
        session = InMemorySessionStore()
        mock_client = MagicMock()
        mock_client.citation_lookup.lookup_text.return_value = [
            {
                "citation": "999 U.S. 9999",
                "status": 404,
                "start_index": 0,
                "end_index": 13,
                "clusters": [],
            },
        ]

        with patch.object(self.tool, "get_client") as mock_get_client:
            mock_get_client.return_value.__enter__ = lambda s: mock_client
            mock_get_client.return_value.__exit__ = MagicMock(
                return_value=False
            )
            result = self.tool({"text": "999 U.S. 9999"}, session)

        assert "NOT FOUND" in result.content[0].text

    def test_no_citations(self):
        session = InMemorySessionStore()
        result = self.tool({"text": "No legal citations here."}, session)
        assert "No citations found" in result.content[0].text

    def test_pending_citations_on_throttle(self):
        """Citations with 429 status should remain pending."""
        session = InMemorySessionStore()
        mock_client = MagicMock()
        mock_client.citation_lookup.lookup_text.return_value = [
            {
                "citation": "576 U.S. 644",
                "status": 200,
                "start_index": 0,
                "end_index": 12,
                "clusters": [
                    {
                        "id": 1,
                        "case_name": "Test",
                        "date_filed": "2020-01-01",
                        "citation_count": 10,
                        "absolute_url": "/opinion/1/test/",
                        "citations": [],
                    }
                ],
            },
            {
                "citation": "388 U.S. 1",
                "status": 429,
                "start_index": 14,
                "end_index": 24,
                "clusters": [],
            },
        ]

        with (
            patch.object(session, "make_id", return_value="abcd1234"),
            patch.object(self.tool, "get_client") as mock_get_client,
        ):
            mock_get_client.return_value.__enter__ = lambda s: mock_client
            mock_get_client.return_value.__exit__ = MagicMock(
                return_value=False
            )
            result = self.tool({"text": SAMPLE_TEXT}, session)

        text = result.content[0].text
        assert "pending" in text.lower()

        job = session.get_citation_analysis("local", "abcd1234")
        assert job is not None
        assert "388 U.S. 1" in job["pending"]
        assert "576 U.S. 644" in job["verified"]


class TestResumeCitationAnalysisTool:
    def setup_method(self):
        self.tool = ResumeCitationAnalysisTool()

    def test_job_not_found(self):
        session = InMemorySessionStore()
        result = self.tool({"job_id": "nonexistent"}, session)
        assert result.isError
        assert "not found" in result.content[0].text.lower()

    def test_already_complete(self):
        session = InMemorySessionStore()
        session.store_citation_analysis(
            "local",
            "abcd1234",
            {
                "resource_refs": {},
                "unique_citations": ["576 U.S. 644"],
                "verified": {"576 U.S. 644": {"status": 200}},
                "pending": [],
            },
        )
        result = self.tool({"job_id": "abcd1234"}, session)
        assert "complete" in result.content[0].text.lower()

    def test_resumes_pending(self):
        session = InMemorySessionStore()
        session.store_citation_analysis(
            "local",
            "abcd1234",
            {
                "resource_refs": {
                    "388 U.S. 1": {
                        "ref_count": 1,
                        "ref_breakdown": "1 full",
                    }
                },
                "unique_citations": [
                    "576 U.S. 644",
                    "388 U.S. 1",
                ],
                "verified": {
                    "576 U.S. 644": {
                        "status": 200,
                        "clusters": [],
                    }
                },
                "pending": ["388 U.S. 1"],
            },
        )

        mock_client = MagicMock()
        mock_client.citation_lookup.lookup_text.return_value = [
            {
                "citation": "388 U.S. 1",
                "status": 200,
                "start_index": 0,
                "end_index": 10,
                "clusters": [
                    {
                        "id": 2,
                        "case_name": "Loving v. Virginia",
                        "date_filed": "1967-06-12",
                        "citation_count": 1523,
                        "absolute_url": "/opinion/2/loving/",
                        "citations": [],
                    }
                ],
            },
        ]

        with patch.object(self.tool, "get_client") as mock_get_client:
            mock_get_client.return_value.__enter__ = lambda s: mock_client
            mock_get_client.return_value.__exit__ = MagicMock(
                return_value=False
            )
            result = self.tool({"job_id": "abcd1234"}, session)

        text = result.content[0].text
        assert "Resumed" in text
        assert "Loving v. Virginia" in text

        job = session.get_citation_analysis("local", "abcd1234")
        assert len(job["pending"]) == 0


class TestCitationUtils:
    def test_canonical_key(self):
        from eyecite import get_citations

        cites = get_citations("576 U.S. 644")
        assert len(cites) == 1
        assert canonical_key(cites[0]) == "576 U.S. 644"

    def test_format_resolved_empty(self):
        from eyecite import get_citations, resolve_citations

        cites = get_citations("No citations here.")
        resolutions = resolve_citations(cites)
        result = format_resolved_citations(cites, resolutions)
        assert "0 citation(s)" in result
