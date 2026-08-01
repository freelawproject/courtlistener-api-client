"""Tool-argument validation and endpoint-ID guidance.

The middleware dispatches to tools directly, so FastMCP never validates
arguments against the schemas we publish (it only validates tools built
from a Python signature). ``MCPTool.validate_arguments`` closes that
gap; the middleware calls it before every dispatch.

Covers the Sentry cluster diagnosed July 2026: a misnamed argument
(``endpoint`` for ``endpoint_id``) surfaced as "Endpoint 'None' not
found", and a top-level ``fields`` on ``call_endpoint`` was silently
dropped rather than rejected.

Also covers the review feedback on PR #209: explicit ``null`` for an
unset optional argument must validate like an omitted key (OpenAI-style
strict tool calling sends nulls, and tool bodies read optionals with
``.get()``), and the schema validator must be built once per tool, not
rebuilt on every call (``search``'s schema costs ~17ms to build).
"""

import pytest
from fastmcp.exceptions import ToolError
from jsonschema import Draft202012Validator

from courtlistener.mcp.tools import MCP_TOOLS
from courtlistener.mcp.tools.utils import endpoint_id_choices
from courtlistener.models import ENDPOINTS
from courtlistener.utils import did_you_mean, validate_model_fields

ENDPOINT_ID_TOOLS = [
    "get_endpoint_schema",
    "get_endpoint_item",
    "call_endpoint",
    "get_choices",
]


class TestToolSchemas:
    @pytest.mark.parametrize("name", sorted(MCP_TOOLS))
    def test_schema_is_valid_and_closed(self, name):
        schema = MCP_TOOLS[name].get_input_schema()
        Draft202012Validator.check_schema(schema)
        assert schema["additionalProperties"] is False, (
            f"{name} accepts unknown arguments, so a misnamed one is "
            f"silently dropped instead of reported"
        )

    @pytest.mark.parametrize("name", ENDPOINT_ID_TOOLS)
    def test_endpoint_id_enumerates_valid_ids(self, name):
        """Every endpoint tool carries the list, not a pointer to another.

        Clients that fetch schemas on demand never see another tool's
        description, so a pointer costs an extra round-trip.
        """
        prop = MCP_TOOLS[name].get_input_schema()["properties"]["endpoint_id"]
        assert "opinions" in prop["enum"]
        assert "opinion" not in prop["enum"]

    def test_only_get_choices_accepts_search_endpoints(self):
        for name in ENDPOINT_ID_TOOLS:
            schema = MCP_TOOLS[name].get_input_schema()
            enum = schema["properties"]["endpoint_id"]["enum"]
            if name == "get_choices":
                assert "search" in enum
            else:
                assert "search" not in enum
                assert not [e for e in enum if e.endswith("-search")]

    def test_call_endpoint_query_stays_open(self):
        """`query` is free-form; Pydantic validates its contents."""
        schema = MCP_TOOLS["call_endpoint"].get_input_schema()
        assert schema["properties"]["query"]["additionalProperties"] is True

    def test_search_endpoints_only_offered_when_included(self):
        assert "search" not in endpoint_id_choices()
        assert "search" in endpoint_id_choices(include_search=True)


class TestValidateArguments:
    def test_misnamed_argument_names_the_real_parameter(self):
        with pytest.raises(ToolError) as excinfo:
            MCP_TOOLS["get_endpoint_schema"].validate_arguments(
                {"endpoint": "search"}
            )
        message = str(excinfo.value)
        assert "'endpoint_id' is a required property" in message
        assert "'endpoint' was unexpected" in message

    def test_unknown_endpoint_id_is_rejected_by_enum(self):
        with pytest.raises(ToolError) as excinfo:
            MCP_TOOLS["get_endpoint_item"].validate_arguments(
                {"endpoint_id": "opinion", "item_id": 217512},
            )
        assert "'opinion' is not one of" in str(excinfo.value)

    def test_missing_required_argument(self):
        with pytest.raises(ToolError) as excinfo:
            MCP_TOOLS["get_endpoint_item"].validate_arguments(
                {"endpoint_id": "opinions"}
            )
        assert "'item_id' is a required property" in str(excinfo.value)

    def test_top_level_fields_on_call_endpoint_is_rejected(self):
        """Previously dropped silently, returning the full payload."""
        with pytest.raises(ToolError) as excinfo:
            MCP_TOOLS["call_endpoint"].validate_arguments(
                {"endpoint_id": "dockets", "fields": ["id", "case_name"]},
            )
        assert "'fields' was unexpected" in str(excinfo.value)

    def test_fields_inside_query_is_accepted(self):
        MCP_TOOLS["call_endpoint"].validate_arguments(
            {
                "endpoint_id": "dockets",
                "query": {"court": "scotus", "fields": ["id", "case_name"]},
            },
        )

    def test_valid_arguments_pass(self):
        MCP_TOOLS["get_endpoint_item"].validate_arguments(
            {"endpoint_id": "opinions", "item_id": 217512, "fields": ["id"]},
        )

    def test_get_choices_accepts_search(self):
        MCP_TOOLS["get_choices"].validate_arguments(
            {"endpoint_id": "search", "field_name": "court"},
        )


class TestExplicitNullArguments:
    @pytest.mark.parametrize(
        "name,arguments",
        [
            (
                "read_document",
                {"opinion_id": 217512, "recap_document_id": None},
            ),
            (
                "call_endpoint",
                {"endpoint_id": "dockets", "query": None, "num_results": None},
            ),
            (
                "create_search_alert",
                {
                    "name": "test",
                    "query": "q=test",
                    "rate": "wly",
                    "alert_type": None,
                },
            ),
            ("search", {"type": "o", "q": "test", "fields": None}),
        ],
    )
    def test_null_for_optional_argument_is_accepted(self, name, arguments):
        MCP_TOOLS[name].validate_arguments(arguments)

    def test_null_for_required_argument_reports_it_missing(self):
        with pytest.raises(ToolError) as excinfo:
            MCP_TOOLS["get_more_results"].validate_arguments(
                {"query_id": None}
            )
        assert "'query_id' is a required property" in str(excinfo.value)

    def test_non_null_violations_still_rejected(self):
        with pytest.raises(ToolError) as excinfo:
            MCP_TOOLS["read_document"].validate_arguments(
                {"opinion_id": "not-an-integer"}
            )
        assert "is not of type 'integer'" in str(excinfo.value)


class TestValidatorCaching:
    def test_validator_is_built_once_per_tool(self):
        tool = MCP_TOOLS["search"]
        assert tool.input_validator is tool.input_validator

    def test_validate_arguments_does_not_rebuild_schema(self, monkeypatch):
        tool = MCP_TOOLS["get_counts"]
        _ = tool.input_validator  # prime the cache
        monkeypatch.setattr(
            type(tool),
            "get_input_schema",
            lambda self: pytest.fail("schema rebuilt on a validation call"),
        )
        tool.validate_arguments({"query_id": "abc12345"})


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


class TestFieldsNormalization:
    """Models pass `fields` as comma/space-separated strings (the
    CourtListener API's own syntax); tool schemas accept the string
    form and `normalize_fields` splits it.
    """

    def test_normalize_comma_separated(self):
        from courtlistener.mcp.tools.utils import normalize_fields

        assert normalize_fields("id,case_name") == ["id", "case_name"]

    def test_normalize_space_and_mixed(self):
        from courtlistener.mcp.tools.utils import normalize_fields

        assert normalize_fields("id case_name") == ["id", "case_name"]
        assert normalize_fields("id, case_name,") == ["id", "case_name"]

    def test_lists_and_none_pass_through(self):
        from courtlistener.mcp.tools.utils import normalize_fields

        assert normalize_fields(["id"]) == ["id"]
        assert normalize_fields(None) is None

    @pytest.mark.parametrize("tool", ["search", "get_endpoint_item"])
    def test_schema_accepts_string_fields(self, tool):
        schema = MCP_TOOLS[tool].get_input_schema()
        anyof = schema["properties"]["fields"]["anyOf"]
        assert {"type": "string"} in anyof

    def test_search_validate_arguments_accepts_comma_string(self):
        MCP_TOOLS["search"].validate_arguments(
            {"type": "o", "q": "test", "fields": "caseName,dateFiled"}
        )
