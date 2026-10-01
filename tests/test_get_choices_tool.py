"""The curated long-choice fields and the get_choices tool that serves them.

Short choice lists are enumerated in every schema they appear in;
only the lists in ``LONG_CHOICE_FIELDS`` are summarized with a pointer
to ``get_choices``. The threshold test below is what forces a decision
when the API grows a new long list.
"""

import pytest
from fastmcp.exceptions import ToolError

from courtlistener.mcp.tools import MCP_TOOLS
from courtlistener.mcp.tools.utils import (
    LONG_CHOICE_FIELDS,
    is_long_choice_field,
    long_choices,
)
from courtlistener.models import ENDPOINTS

# Above this many choices a field must be curated (or consciously left
# inline) rather than silently enumerated into every schema.
LONG_CHOICE_THRESHOLD = 40


def _choice_fields():
    """Every (endpoint_id, field_name, choices) the MCP can expose."""
    for model in ENDPOINTS.values():
        endpoint_id = model.endpoint_id
        if endpoint_id.endswith("-search"):
            continue  # per-type search models duplicate `search`
        for field_name, field in model.model_fields.items():
            extra = field.json_schema_extra
            choices = extra.get("choices") if isinstance(extra, dict) else None
            if choices and field_name != "fields":
                yield endpoint_id, field_name, choices


class TestLongChoiceCuration:
    def test_every_long_list_has_a_curation_decision(self):
        uncurated = [
            f"{endpoint_id}.{field_name} ({len(choices)} choices)"
            for endpoint_id, field_name, choices in _choice_fields()
            if len(choices) > LONG_CHOICE_THRESHOLD
            and not is_long_choice_field(endpoint_id, field_name)
        ]
        assert not uncurated, (
            "Choice lists longer than the threshold must be added to "
            "LONG_CHOICE_FIELDS (served by get_choices) or the threshold "
            f"raised deliberately: {uncurated}"
        )

    def test_curated_entries_exist_and_are_long(self):
        for field_name, endpoint_ids in LONG_CHOICE_FIELDS.items():
            for endpoint_id in endpoint_ids:
                model = next(
                    m
                    for m in ENDPOINTS.values()
                    if m.endpoint_id == endpoint_id
                )
                extra = model.model_fields[field_name].json_schema_extra
                assert len(extra["choices"]) > LONG_CHOICE_THRESHOLD, (
                    f"{endpoint_id}.{field_name} no longer needs get_choices"
                )

    def test_curated_lists_agree_across_endpoints(self):
        """A name-only lookup is only honest if the value sets match."""
        for field_name, endpoint_ids in LONG_CHOICE_FIELDS.items():
            value_sets = {
                frozenset(
                    c["value"]
                    for c in next(
                        m for m in ENDPOINTS.values() if m.endpoint_id == eid
                    )
                    .model_fields[field_name]
                    .json_schema_extra["choices"]
                )
                for eid in endpoint_ids
            }
            assert len(value_sets) == 1, field_name

    def test_short_lists_are_not_curated(self):
        assert not is_long_choice_field("clusters", "source")
        assert not is_long_choice_field("dockets", "order_by")


class TestGetChoices:
    def test_schema_offers_only_the_curated_fields(self):
        schema = MCP_TOOLS["get_choices"].get_input_schema()
        assert list(schema["properties"]) == ["field_name"]
        assert schema["properties"]["field_name"]["enum"] == sorted(
            LONG_CHOICE_FIELDS
        )
        assert (
            "`court` (search)"
            in schema["properties"]["field_name"]["description"]
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("field_name", sorted(LONG_CHOICE_FIELDS))
    async def test_returns_the_full_list(self, field_name):
        result = await MCP_TOOLS["get_choices"].call(
            {"field_name": field_name}
        )
        assert result["choices"] == long_choices(field_name)
        assert len(result["choices"]) > LONG_CHOICE_THRESHOLD
        assert {"value", "display_name"} <= set(result["choices"][0])

    @pytest.mark.asyncio
    async def test_court_includes_scotus(self):
        result = await MCP_TOOLS["get_choices"].call({"field_name": "court"})
        assert "scotus" in {c["value"] for c in result["choices"]}

    def test_other_fields_are_rejected_with_the_valid_names(self):
        with pytest.raises(ToolError) as excinfo:
            MCP_TOOLS["get_choices"].validate_arguments(
                {"field_name": "nature_of_suit"}
            )
        assert "'nature_of_suit' is not one of" in str(excinfo.value)
        assert "position_type" in str(excinfo.value)

    def test_endpoint_id_is_no_longer_an_argument(self):
        with pytest.raises(ToolError) as excinfo:
            MCP_TOOLS["get_choices"].validate_arguments(
                {"endpoint_id": "search", "field_name": "court"}
            )
        assert "'endpoint_id' was unexpected" in str(excinfo.value)


class TestSchemasEnumerateInline:
    def test_search_court_points_at_get_choices_by_name(self):
        desc = MCP_TOOLS["search"].get_input_schema()["properties"]["court"][
            "description"
        ]
        assert "470 valid choices" in desc
        assert 'field_name="court"' in desc
        assert "endpoint_id" not in desc

    @pytest.mark.asyncio
    async def test_short_lists_are_enumerated_in_full(self):
        schema = await MCP_TOOLS["get_endpoint_schema"].call(
            {"endpoint_id": "clusters"}
        )
        desc = schema["properties"]["source"]["description"]
        assert "Valid choices:" in desc
        assert "get_choices" not in desc

    @pytest.mark.asyncio
    async def test_fields_lists_are_never_truncated(self):
        schema = await MCP_TOOLS["get_endpoint_schema"].call(
            {"endpoint_id": "dockets"}
        )
        desc = schema["properties"]["fields"]["description"]
        assert "Valid choices:" in desc
        assert "get_choices" not in desc
        assert '"value": "docket_number_core"' in desc

    @pytest.mark.asyncio
    async def test_long_lists_in_endpoint_schemas_point_at_get_choices(self):
        schema = await MCP_TOOLS["get_endpoint_schema"].call(
            {"endpoint_id": "dockets"}
        )
        desc = schema["properties"]["source"]["description"]
        assert "255 valid choices" in desc
        assert 'field_name="source"' in desc
