"""Tests for helpers in ``courtlistener.utils``."""

import json

import pytest

from courtlistener.models import ENDPOINTS
from courtlistener.utils import (
    did_you_mean,
    inline_refs,
    validate_model_fields,
)


class TestInlineRefs:
    def test_inlines_a_simple_ref(self):
        defs = {
            "Filter6": {
                "type": "object",
                "properties": {"contains": {"type": "string"}},
            }
        }
        node = {"anyOf": [{"type": "string"}, {"$ref": "#/$defs/Filter6"}]}
        out = inline_refs(node, defs)
        assert out == {
            "anyOf": [
                {"type": "string"},
                {
                    "type": "object",
                    "properties": {"contains": {"type": "string"}},
                },
            ]
        }
        assert "$ref" not in json.dumps(out)

    def test_preserves_sibling_keys(self):
        defs = {"F": {"type": "object"}}
        node = {"$ref": "#/$defs/F", "description": "hi"}
        out = inline_refs(node, defs)
        assert out == {"type": "object", "description": "hi"}

    def test_breaks_reference_cycles(self):
        # F references itself; inlining must terminate.
        defs = {"F": {"properties": {"self": {"$ref": "#/$defs/F"}}}}
        out = inline_refs({"$ref": "#/$defs/F"}, defs)
        assert "$ref" not in json.dumps(out)

    def test_unknown_ref_becomes_empty(self):
        assert inline_refs({"$ref": "#/$defs/Missing"}, {}) == {}


def _field_choices(endpoint_id: str) -> list[str]:
    """The returnable field names, as ``validate_model_fields`` sees them.

    Distinct from ``model_fields``, which holds the filter parameters.
    """
    extra = ENDPOINTS[endpoint_id].model_fields["fields"].json_schema_extra
    return [choice["value"] for choice in extra["choices"]]


class TestDidYouMean:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("citation", "citations"),
            ("nonparticipating_judges", "non_participating_judges"),
            ("case_nam", "case_name"),
        ],
    )
    def test_suggests_near_misses(self, value, expected):
        assert expected in did_you_mean(value, _field_choices("clusters"))

    def test_silent_when_nothing_is_close(self):
        assert did_you_mean("zzzzzz", ["citations", "case_name"]) == ""


class TestFieldErrors:
    def test_invalid_field_suggests_the_plural(self):
        """The `citation` -> `citations` mistake, from search output."""
        with pytest.raises(ValueError) as excinfo:
            validate_model_fields(ENDPOINTS["clusters"], ["citation"])
        message = str(excinfo.value)
        assert "Did you mean: citations" in message
        assert "Fields must be one of:" in message

    def test_deprecated_field_still_lists_valid_fields(self):
        """No close match; the message must stay useful anyway."""
        with pytest.raises(ValueError) as excinfo:
            validate_model_fields(ENDPOINTS["clusters"], ["federal_cite_one"])
        message = str(excinfo.value)
        assert "Did you mean" not in message
        assert "Fields must be one of:" in message

    def test_filter_name_requested_as_field_gets_hint(self):
        with pytest.raises(ValueError) as excinfo:
            validate_model_fields(ENDPOINTS["parties"], ["id", "docket"])
        assert "`docket` is a filter on this endpoint" in str(excinfo.value)
