"""Unit tests for citation analysis helpers."""

from __future__ import annotations

from courtlistener.mcp.tools.citation_utils import format_analysis


class TestFormatAnalysisTerminology:
    """Issue #123: the header must distinguish citation occurrences from
    unique citation strings from unique case clusters.
    """

    def test_extraction_line_uses_new_terminology(self):
        out = format_analysis(
            analysis_id="abc123",
            cites=[],
            resolutions={},
            resource_refs={},
            unique_citations=["347 U.S. 483", "372 U.S. 335"],
            verified={},
            pending=[],
        )
        assert "citation occurrence" in out
        assert "unique citation string" in out
