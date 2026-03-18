"""Tests for the citation MCP tools."""

from unittest.mock import MagicMock, patch

from courtlistener.mcp.tools.analyze_citations_tool import AnalyzeCitationsTool
from courtlistener.mcp.tools.citation_utils import (
    build_compact_string,
    canonical_key,
    extract_unique_case_citations,
    format_flat_citations,
    format_resolved_citations,
    summarize_cluster,
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
        session = {}
        result = self.tool({"text": SAMPLE_TEXT}, session)
        text = result.content[0].text
        assert "576 U.S. 644" in text
        assert "388 U.S. 1" in text
        assert "42 U.S.C. § 1983" in text
        assert "unique case(s)" in text

    def test_flat_output(self):
        session = {}
        result = self.tool({"text": SAMPLE_TEXT, "resolve": False}, session)
        text = result.content[0].text
        assert "[full]" in text
        assert "576 U.S. 644" in text

    def test_no_citations(self):
        session = {}
        result = self.tool({"text": "No legal citations here."}, session)
        assert "No citations found" in result.content[0].text

    def test_stateless(self):
        """extract_citations should not modify session."""
        session = {}
        self.tool({"text": SAMPLE_TEXT}, session)
        assert session == {}


class TestAnalyzeCitationsTool:
    def setup_method(self):
        self.tool = AnalyzeCitationsTool()

    def _mock_api_results(self, *citations_and_statuses):
        """Build mock API results for given (citation, status) pairs."""
        results = []
        for citation, status in citations_and_statuses:
            result = {
                "citation": citation,
                "status": status,
                "start_index": 0,
                "end_index": len(citation),
                "clusters": [],
                "error_message": "",
            }
            if status == 200:
                result["clusters"] = [
                    {
                        "id": 12345,
                        "case_name": f"Test Case for {citation}",
                        "case_name_short": "Test",
                        "date_filed": "2020-01-01",
                        "citation_count": 42,
                        "precedential_status": "Published",
                        "absolute_url": "/opinion/12345/test/",
                        "docket": 999,
                        "citations": [
                            {
                                "volume": citation.split()[0],
                                "reporter": " ".join(citation.split()[1:-1]),
                                "page": citation.split()[-1],
                            }
                        ],
                    }
                ]
            return results, result
        return results

    def test_stores_in_session(self):
        """analyze_citations should store results in session."""
        session = {}
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

        with patch.object(self.tool, "get_client") as mock_get_client:
            mock_get_client.return_value.__enter__ = lambda s: mock_client
            mock_get_client.return_value.__exit__ = MagicMock(
                return_value=False
            )
            result = self.tool({"text": SAMPLE_TEXT}, session)

        text = result.content[0].text
        assert "Job ID: 1" in text
        assert "citation_analyses" in session
        assert 1 in session["citation_analyses"]

        job = session["citation_analyses"][1]
        assert "576 U.S. 644" in job["verified"]
        assert "388 U.S. 1" in job["verified"]
        assert len(job["pending"]) == 0

    def test_output_contains_case_details(self):
        """Verified cases should show name, date, and URL."""
        session = {}
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
        session = {}
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
        session = {}
        result = self.tool({"text": "No legal citations here."}, session)
        assert "No citations found" in result.content[0].text

    def test_pending_citations_on_throttle(self):
        """Citations with 429 status should remain pending."""
        session = {}
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

        with patch.object(self.tool, "get_client") as mock_get_client:
            mock_get_client.return_value.__enter__ = lambda s: mock_client
            mock_get_client.return_value.__exit__ = MagicMock(
                return_value=False
            )
            result = self.tool({"text": SAMPLE_TEXT}, session)

        text = result.content[0].text
        assert "pending" in text.lower()

        job = session["citation_analyses"][1]
        assert "388 U.S. 1" in job["pending"]
        assert "576 U.S. 644" in job["verified"]


class TestResumeCitationAnalysisTool:
    def setup_method(self):
        self.tool = ResumeCitationAnalysisTool()

    def test_job_not_found(self):
        session = {}
        result = self.tool({"job_id": 99}, session)
        assert result.isError
        assert "not found" in result.content[0].text.lower()

    def test_already_complete(self):
        session = {
            "citation_analyses": {
                1: {
                    "resource_refs": {},
                    "unique_citations": ["576 U.S. 644"],
                    "verified": {"576 U.S. 644": {"status": 200}},
                    "pending": [],
                }
            }
        }
        result = self.tool({"job_id": 1}, session)
        assert "complete" in result.content[0].text.lower()

    def test_resumes_pending(self):
        session = {
            "citation_analyses": {
                1: {
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
                }
            }
        }

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
            result = self.tool({"job_id": 1}, session)

        text = result.content[0].text
        assert "Resumed" in text
        assert "Loving v. Virginia" in text
        assert len(session["citation_analyses"][1]["pending"]) == 0


class TestCitationUtils:
    def test_canonical_key(self):
        from eyecite import get_citations

        cites = get_citations("576 U.S. 644")
        assert len(cites) == 1
        assert canonical_key(cites[0]) == "576 U.S. 644"

    def test_build_compact_string(self):
        result = build_compact_string(["576 U.S. 644", "388 U.S. 1"])
        assert result == "576 U.S. 644; 388 U.S. 1"

    def test_extract_unique_case_citations(self):
        from eyecite import get_citations, resolve_citations

        cites = get_citations(SAMPLE_TEXT)
        resolutions = resolve_citations(cites)
        unique = extract_unique_case_citations(resolutions)
        assert "576 U.S. 644" in unique
        assert "388 U.S. 1" in unique
        assert len(unique) == 2  # statutes excluded

    def test_summarize_cluster(self):
        cluster = {
            "id": 12345,
            "case_name": "Test Case",
            "case_name_short": "Test",
            "date_filed": "2020-01-01",
            "citation_count": 42,
            "precedential_status": "Published",
            "absolute_url": "/opinion/12345/test/",
            "docket": 999,
            "citations": [
                {"volume": "576", "reporter": "U.S.", "page": "644"}
            ],
            # These bloated fields should be excluded
            "attorneys": "long attorney string...",
            "html_with_citations": "<html>very long...</html>",
        }
        summary = summarize_cluster(cluster)
        assert summary["cluster_id"] == 12345
        assert summary["case_name"] == "Test Case"
        assert summary["citations"] == ["576 U.S. 644"]
        assert "attorneys" not in summary
        assert "html_with_citations" not in summary

    def test_format_flat_no_citations(self):
        assert format_flat_citations([]) == "No citations found."

    def test_format_resolved_empty(self):
        from eyecite import get_citations, resolve_citations

        cites = get_citations("No citations here.")
        resolutions = resolve_citations(cites)
        result = format_resolved_citations(cites, resolutions)
        assert "0 citation(s)" in result
