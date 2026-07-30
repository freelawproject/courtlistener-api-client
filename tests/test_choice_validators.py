"""Unit tests for choice validation, especially the space-separated
fallback on multiple-choice fields like search's `court`.

Models frequently pass `court="scotus ca1"` (CourtListener's own
search API convention), which used to fail validation because the
whole string was looked up as a single choice. The fallback splits
such strings only when every token is an exact choice VALUE, so
multi-word display names ("Supreme Court of the United States") are
never misread as lists.
"""

import pytest
from pydantic import ValidationError

from courtlistener.models import ENDPOINTS
from courtlistener.models.endpoints.opinion_search import (
    OpinionSearchEndpoint,
)
from courtlistener.utils import multiple_choice_validator


def uses_multiple_choice_validator(field) -> bool:
    return any(
        getattr(meta, "func", None) is multiple_choice_validator
        for meta in field.metadata
    )


def court_of(**kwargs):
    return OpinionSearchEndpoint(type="o", **kwargs).court


class TestCourtChoiceValidation:
    def test_single_value(self):
        assert court_of(court="scotus") == "scotus"

    def test_list_of_values(self):
        assert court_of(court=["scotus", "ca1"]) == ["scotus", "ca1"]

    def test_space_separated_values(self):
        assert court_of(court="scotus ca1") == ["scotus", "ca1"]

    def test_comma_separated_values(self):
        assert court_of(court="scotus,ca1") == ["scotus", "ca1"]

    def test_comma_space_separated_values(self):
        assert court_of(court="scotus, ca1") == ["scotus", "ca1"]

    def test_comma_containing_label_matches_whole(self):
        assert court_of(court="District Court, D. Alaska") == "akd"

    def test_space_separated_many(self):
        assert court_of(court="scotus ca1 ca2 cand") == [
            "scotus",
            "ca1",
            "ca2",
            "cand",
        ]

    def test_display_name_matches_whole(self):
        assert court_of(court="Supreme Court of the United States") == "scotus"

    def test_display_name_inside_list(self):
        assert court_of(
            court=["Supreme Court of the United States", "ca1"]
        ) == ["scotus", "ca1"]

    def test_trailing_comma_single_value(self):
        assert court_of(court="scotus,") == "scotus"

    def test_leading_and_trailing_space_single_value(self):
        assert court_of(court=" scotus ") == "scotus"

    def test_display_name_with_trailing_comma(self):
        assert (
            court_of(court="Supreme Court of the United States,") == "scotus"
        )

    def test_space_separated_with_invalid_token_fails(self):
        with pytest.raises(ValidationError, match="scotus banana"):
            court_of(court="scotus banana")

    def test_single_invalid_value_fails(self):
        with pytest.raises(ValidationError, match="Invalid value"):
            court_of(court="not-a-court")

    def test_display_names_are_not_split(self):
        # A multi-word string that is neither a display name nor
        # all-valid-values must fail, not partially match.
        with pytest.raises(ValidationError, match="Invalid value"):
            court_of(court="Supreme Court")


def test_no_multiple_choice_value_contains_whitespace():
    """Invariant the fallback relies on: on fields validated by
    `multiple_choice_validator`, choice VALUES never contain
    whitespace, so token-wise value matching can never collide with a
    display name. (Single-choice fields like `order_by` legitimately
    have values with spaces -- "score desc" -- and are exempt.) If
    this ever fails, the space-separated fallback in
    `multiple_choice_validator` must be revisited.
    """
    checked = 0
    for endpoint in ENDPOINTS.values():
        for name, field in endpoint.model_fields.items():
            if not uses_multiple_choice_validator(field):
                continue
            checked += 1
            extra = getattr(field, "json_schema_extra", None) or {}
            for choice in extra.get("choices", []):
                value = choice["value"]
                assert not (
                    isinstance(value, str)
                    and any(c.isspace() or c == "," for c in value)
                ), (
                    f"{endpoint.__name__}.{name} has a choice value "
                    f"with whitespace or comma: {value!r}"
                )
    assert checked > 0, "no multiple-choice fields found; detection broken?"


class TestIntChoiceFields:
    """Int-keyed choice fields (e.g. prayers `status`) get the same
    separated-string and stringified-number tolerance."""

    def prayers_status(self, **kwargs):
        from courtlistener.models.endpoints.prayers import PrayersEndpoint

        return PrayersEndpoint(**kwargs).status

    def test_int_value_unchanged(self):
        assert self.prayers_status(status=1) == 1

    def test_stringified_int(self):
        assert self.prayers_status(status="1") == 1

    def test_space_separated_ints(self):
        # Multi-value REST filters serialize to the `__in` lookup form;
        # the separated string must land identically to a real list.
        assert self.prayers_status(status="1 2") == self.prayers_status(
            status=[1, 2]
        )

    def test_comma_separated_ints(self):
        assert self.prayers_status(status="1,2") == self.prayers_status(
            status=[1, 2]
        )

    def test_invalid_int_fails(self):
        with pytest.raises(ValidationError, match="Invalid value"):
            self.prayers_status(status="99")


class TestRelatedPassthrough:
    """Sentry MCP-1J: related filters whose target has no standalone
    endpoint (clusters.citations -> Citation) crashed with
    AttributeError because FieldInfo.json_schema_extra defaults to None
    (the attribute always exists, so a getattr default never applies).
    Such fields now pass the sub-filter dict through unvalidated; the
    API validates server-side.
    """

    def test_citations_dict_passes_through(self):
        from courtlistener.models.endpoints.clusters import ClustersEndpoint

        model = ClustersEndpoint(citations={"page": "60", "volume": "662"})
        assert model.citations == {"page": "60", "volume": "662"}

    def test_none_subfilters_dropped(self):
        from courtlistener.models.endpoints.clusters import ClustersEndpoint

        model = ClustersEndpoint(citations={"volume": "662", "page": None})
        assert model.citations == {"volume": "662"}

    def test_non_dict_still_rejected(self):
        from courtlistener.models.endpoints.clusters import ClustersEndpoint

        with pytest.raises(ValidationError, match="citations"):
            ClustersEndpoint(citations=[1, 2])

    def test_validated_related_field_still_validates(self):
        from courtlistener.models.endpoints.clusters import ClustersEndpoint

        # docket resolves to DocketsEndpoint and must keep validating.
        with pytest.raises(ValidationError):
            ClustersEndpoint(docket={"not_a_real_docket_field": 1})


class TestDidYouMeanErrors:
    """Invalid-choice errors suggest near misses instead of dumping the
    full choice dict (court alone is 470 entries / ~10k chars). The bad
    ids here are the most common model hallucinations from Sentry MCP-G.
    """

    def error_for(self, court):
        with pytest.raises(ValidationError) as exc_info:
            court_of(court=court)
        return str(exc_info.value)

    @pytest.mark.parametrize(
        "bad,expected_suggestion",
        [
            ("njsupct", "nysupct"),
            ("texapp2", "texapp"),
            ("fladistctapp1", "fladistctapp"),
            ("ganctapp", "gactapp"),
            ("okno", "oknd"),
        ],
    )
    def test_hallucinated_ids_get_suggestions(self, bad, expected_suggestion):
        msg = self.error_for(bad)
        assert "Did you mean" in msg
        assert expected_suggestion in msg

    def test_choice_dict_not_dumped(self):
        msg = self.error_for("njsupct")
        assert "Supreme Court of the United States" not in msg
        assert len(msg) < 600

    def test_mixed_tokens_suggest_only_invalid(self):
        # 'scotus' is valid; suggestions should target 'texapp2' only.
        msg = self.error_for("scotus texapp2")
        assert "texapp" in msg
        assert "Did you mean" in msg

    def test_points_to_get_choices(self):
        assert "get_choices" in self.error_for("njsupct")

    def test_single_choice_field_also_compact(self):
        from courtlistener.models.endpoints.opinion_search import (
            OpinionSearchEndpoint,
        )

        with pytest.raises(ValidationError) as exc_info:
            OpinionSearchEndpoint(type="o", order_by="relevance desc")
        msg = str(exc_info.value)
        assert "Did you mean" in msg or "get_choices" in msg
        assert len(msg) < 600


class TestSuggestionQuality:
    """Review nits on PR 228: case-only mismatches must still get
    suggestions, and multi-word typos must be matched whole rather
    than split into per-word suggestion noise.
    """

    def error_for(self, court):
        with pytest.raises(ValidationError) as exc_info:
            court_of(court=court)
        return str(exc_info.value)

    def test_case_only_mismatch_gets_suggestion(self):
        msg = self.error_for("SCOTUS")
        assert "scotus" in msg

    def test_multiword_typo_matched_whole(self):
        msg = self.error_for("Supreme Court")
        # Whole-string matches, not per-word fragments.
        assert "Supreme Court" in msg.split("Did you mean")[1]
        assert "prsupreme" not in msg
        assert "ortc" not in msg

    def test_comma_containing_typo_matched_whole(self):
        msg = self.error_for("District Court, D. Nonexistent")
        assert "District Court, D." in msg.split("Did you mean")[1]

    def test_genuine_list_still_suggests_per_token(self):
        msg = self.error_for("scotus texapp2")
        assert "texapp" in msg
