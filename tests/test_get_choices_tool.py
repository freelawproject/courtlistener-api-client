"""Behavior tests for the get_choices tool (Sentry MCP-N).

Asking for choices on a field that has none is routine model
exploration -- ~70% of MCP-N was `nature_of_suit`, which models
reasonably assume is enumerable (PACER's NOS codes are a fixed
taxonomy) but CL stores as free text. The tool now answers those
questions instead of raising, and misnamed fields raise a
Sentry-exempt error with suggestions.
"""

import pytest

from courtlistener.mcp.tools import MCP_TOOLS


class FakeContext:
    pass


async def call(**arguments):
    return await MCP_TOOLS["get_choices"](arguments, FakeContext())


class TestGetChoices:
    @pytest.mark.asyncio
    async def test_field_with_choices(self):
        result = await call(endpoint_id="search", field_name="court")
        assert {
            k: v for k, v in result["choices"][0].items() if k == "value"
        } == {"value": "scotus"}

    @pytest.mark.asyncio
    async def test_free_text_field_answers_instead_of_erroring(self):
        result = await call(endpoint_id="search", field_name="nature_of_suit")
        assert result["choices"] == []
        assert "no fixed choice list" in result["note"]
        assert (
            "court" in result["note"]
        )  # points at fields that DO have choices

    @pytest.mark.asyncio
    async def test_related_field_gets_related_guidance(self):
        result = await call(endpoint_id="dockets", field_name="court")
        assert result["choices"] == []
        assert "related-object filter" in result["note"]

    @pytest.mark.asyncio
    async def test_unknown_field_errors_with_suggestion(self):
        with pytest.raises(ValueError) as exc_info:
            await call(
                endpoint_id="people", field_name="political_affiliation"
            )
        assert "political_affiliations" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_literal_field_reports_fixed_value(self):
        result = await call(endpoint_id="opinion-search", field_name="type")
        assert result["choices"] == [{"value": "o", "display_name": "o"}]
        assert "fixed to 'o'" in result["note"]

    @pytest.mark.asyncio
    async def test_related_field_description_generated(self):
        from courtlistener.models.endpoints.dockets import DocketsEndpoint

        desc = DocketsEndpoint.model_fields["court"].description
        assert "Related filter" in desc
        assert "court__" in desc
        assert "Not an enumerated choice field" in desc
