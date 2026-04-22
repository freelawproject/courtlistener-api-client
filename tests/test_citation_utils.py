"""Unit tests for citation analysis helpers."""

from __future__ import annotations

from courtlistener.mcp.tools.citation_utils import (
    CASE_NAME_MATCH_THRESHOLD,
    case_name_mismatch,
    case_name_similarity,
    format_analysis,
    format_verification_result,
    normalize_case_name,
)


class TestNormalizeCaseName:
    def test_lowercases_and_strips_punctuation(self):
        assert normalize_case_name("Brown v. Board") == "brown v board"

    def test_collapses_vs_variants(self):
        assert normalize_case_name("Brown vs. Board") == "brown v board"
        assert normalize_case_name("Brown versus Board") == "brown v board"
        assert normalize_case_name("Brown VS Board") == "brown v board"

    def test_empty_and_none_return_empty_string(self):
        assert normalize_case_name(None) == ""
        assert normalize_case_name("") == ""
        assert normalize_case_name("   ") == ""


class TestCaseNameSimilarity:
    def test_identical_names_score_one(self):
        assert case_name_similarity("Gideon v. Wainwright", "Gideon v. Wainwright") == 1.0

    def test_short_form_subset_scores_one(self):
        # Common real-world case: input uses short form, canonical is full.
        assert case_name_similarity(
            "Brown v. Board", "Brown v. Board of Education"
        ) == 1.0

    def test_hallucinated_name_scores_low(self):
        # Issue #122 reproducer.
        score = case_name_similarity("Case0 v. Other0", "United States v. Agurs")
        assert score < CASE_NAME_MATCH_THRESHOLD

    def test_unrelated_names_score_low(self):
        assert case_name_similarity("Roe v. Wade", "Doe v. Bolton") < CASE_NAME_MATCH_THRESHOLD

    def test_empty_input_scores_zero(self):
        assert case_name_similarity(None, "Brown v. Board") == 0.0
        assert case_name_similarity("Brown v. Board", "") == 0.0

    def test_generic_prosecutor_prefix_does_not_inflate(self):
        # "United States v. X" is common; the shared "United States v."
        # prefix must not mask a different defendant.
        score = case_name_similarity(
            "United States v. Agurs", "United States v. Morrison"
        )
        assert score < CASE_NAME_MATCH_THRESHOLD

    def test_state_prefix_does_not_inflate(self):
        score = case_name_similarity("State v. Smith", "State v. Jones")
        assert score < CASE_NAME_MATCH_THRESHOLD

    def test_same_generic_prosecutor_still_matches_on_defendant(self):
        assert case_name_similarity(
            "United States v. Agurs", "United States v. Agurs"
        ) == 1.0

    def test_typo_tolerance_preserved(self):
        # Single-char typo in defendant must not trip the warning.
        assert case_name_similarity(
            "Smith v. Jones", "Smith v. Jone"
        ) >= CASE_NAME_MATCH_THRESHOLD


class TestCaseNameMismatch:
    @staticmethod
    def _found(name):
        return {"status": 200, "clusters": [{"case_name": name}]}

    def test_matching_names_no_mismatch(self):
        assert case_name_mismatch(
            self._found("Brown v. Board of Education"), "Brown v. Board"
        ) is False

    def test_hallucinated_name_is_mismatch(self):
        assert case_name_mismatch(
            self._found("United States v. Agurs"), "Case0 v. Other0"
        ) is True

    def test_missing_input_name_no_mismatch(self):
        assert case_name_mismatch(self._found("Brown v. Board"), None) is False

    def test_non_found_status_no_mismatch(self):
        assert case_name_mismatch(
            {"status": 404, "clusters": []}, "Brown v. Board"
        ) is False


class TestFormatVerificationResultFoundBranch:
    def test_found_with_matching_name_no_warning(self):
        result = {
            "status": 200,
            "clusters": [{
                "cluster_id": 42,
                "case_name": "Brown v. Board of Education",
                "date_filed": "1954-05-17",
                "citation_count": 999,
            }],
        }
        out = format_verification_result(
            "347 U.S. 483", result, 1, "1 full", 1,
            input_case_name="Brown v. Board",
        )
        assert "WARNING" not in out
        assert "Cluster ID: 42" in out

    def test_found_with_hallucinated_name_emits_warning(self):
        result = {
            "status": 200,
            "clusters": [{
                "cluster_id": 555,
                "case_name": "United States v. Agurs",
                "date_filed": "1976-06-24",
                "citation_count": 1523,
            }],
        }
        out = format_verification_result(
            "427 U.S. 97", result, 1, "1 full", 1,
            input_case_name="Case0 v. Other0",
        )
        assert "WARNING" in out
        assert "Case0 v. Other0" in out
        assert "United States v. Agurs" in out

    def test_found_without_input_name_no_warning(self):
        result = {
            "status": 200,
            "clusters": [{
                "cluster_id": 42,
                "case_name": "Brown v. Board of Education",
                "citation_count": 999,
            }],
        }
        out = format_verification_result(
            "347 U.S. 483", result, 1, "1 full", 1, input_case_name=None,
        )
        assert "WARNING" not in out


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


class TestFormatAnalysisMismatchSummary:
    """Issue #122: a top-level summary line must count citations whose
    verified case name disagrees with the input name.
    """

    def test_mismatch_summary_counts_hallucinations(self):
        verified = {
            "427 U.S. 97": {
                "status": 200,
                "clusters": [{"cluster_id": 1, "case_name": "United States v. Agurs"}],
            },
        }
        input_case_names = {"427 U.S. 97": "Case0 v. Other0"}
        out = format_analysis(
            analysis_id="abc123",
            cites=[],
            resolutions={},
            resource_refs={},
            unique_citations=["427 U.S. 97"],
            verified=verified,
            pending=[],
            input_case_names=input_case_names,
        )
        assert "WARNING: 1 citation" in out
