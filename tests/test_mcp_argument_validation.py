"""Tool-argument validation and endpoint-ID guidance.

FastMCP only validates arguments for tools built from a Python
signature, so ``MCPTool.validate_arguments`` checks them against the
schema we publish; ``MCPTool.run`` calls it before every dispatch.

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

from courtlistener.mcp.exceptions import ToolArgumentValidationError
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

    def test_search_type_is_optional_and_defaults_to_opinions(self):
        schema = MCP_TOOLS["search"].get_input_schema()
        assert "type" not in schema.get("required", [])
        assert schema["properties"]["type"]["default"] == "o"
        MCP_TOOLS["search"].validate_arguments({"q": "test"})

    def test_search_endpoint_type_defaults_to_opinions(self):
        assert ENDPOINTS["search"]().type == "o"
        assert ENDPOINTS["search"](type="r").type == "r"


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


class TestArgumentAliases:
    """`search` takes `q`, `search_document` takes `query`; models swap
    them (Sentry, issue #267), so each tolerates the other's name.
    """

    @pytest.mark.parametrize(
        "tool,arguments,expected",
        [
            ("search", {"query": "privacy"}, {"q": "privacy"}),
            (
                "search_document",
                {"opinion_id": 1, "q": "privacy"},
                {"opinion_id": 1, "query": "privacy"},
            ),
        ],
    )
    def test_alias_renamed_and_validates(self, tool, arguments, expected):
        resolved = MCP_TOOLS[tool].resolve_argument_aliases(arguments)
        assert resolved == expected
        MCP_TOOLS[tool].validate_arguments(resolved)

    def test_alias_not_advertised(self):
        search = MCP_TOOLS["search"].parameters["properties"]
        search_document = MCP_TOOLS["search_document"].parameters["properties"]
        assert "query" not in search
        assert "q" not in search_document

    @pytest.mark.parametrize(
        "tool,arguments",
        [
            ("search", {"type": "o", "q": "privacy", "court": "scotus"}),
            ("search_document", {"opinion_id": 1, "query": "privacy"}),
            ("call_endpoint", {"endpoint_id": "dockets", "query": {}}),
            ("create_search_alert", {"name": "x", "query": "q=test"}),
        ],
    )
    def test_canonical_arguments_untouched(self, tool, arguments):
        resolved = MCP_TOOLS[tool].resolve_argument_aliases(arguments)
        assert resolved == arguments

    def test_conflicting_values_rejected(self):
        with pytest.raises(ToolArgumentValidationError) as excinfo:
            MCP_TOOLS["search"].resolve_argument_aliases(
                {"q": "privacy", "query": "speech"}
            )
        assert "`query` is an alias for `q`" in str(excinfo.value)
        assert excinfo.value.argument_names == ["q", "query"]

    @pytest.mark.parametrize(
        "arguments",
        [
            {"q": "privacy", "query": "privacy"},
            {"q": None, "query": "privacy"},
            {"q": "privacy", "query": None},
        ],
    )
    def test_identical_or_null_double_supply_accepted(self, arguments):
        resolved = MCP_TOOLS["search"].resolve_argument_aliases(arguments)
        assert resolved == {"q": "privacy"}

    @pytest.mark.asyncio
    async def test_run_passes_renamed_arguments(self, monkeypatch):
        tool = MCP_TOOLS["search_document"]
        seen = {}

        async def fake_call(self, arguments):
            seen.update(arguments)
            return {}

        monkeypatch.setattr(type(tool), "call", fake_call)
        await tool.run({"opinion_id": 1, "q": "privacy"})
        assert seen == {"opinion_id": 1, "query": "privacy"}


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

    def test_filter_name_requested_as_field_gets_hint(self):
        with pytest.raises(ValueError) as excinfo:
            validate_model_fields(ENDPOINTS["parties"], ["id", "docket"])
        assert "`docket` is a filter on this endpoint" in str(excinfo.value)


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


class TestJsonEncodedArguments:
    """Some clients send arrays and ints as JSON text (Sentry MCP-75)."""

    @pytest.mark.parametrize(
        "tool,name,raw,expected",
        [
            (
                "get_endpoint_item",
                "fields",
                '["id", "full_name"]',
                ["id", "full_name"],
            ),
            ("search", "court", '["scotus", "ca4"]', ["scotus", "ca4"]),
            ("search_document", "opinion_id", "[15, 85]", [15, 85]),
            ("search_document", "opinion_id", "9429294", 9429294),
            ("read_document", "chunk_index", "[0, 1, 2]", [0, 1, 2]),
            (
                "call_endpoint",
                "query",
                '{"court": "scotus"}',
                {"court": "scotus"},
            ),
        ],
    )
    def test_decodes(self, tool, name, raw, expected):
        decoded = MCP_TOOLS[tool].decode_json_arguments({name: raw})
        assert decoded[name] == expected

    @pytest.mark.parametrize(
        "tool,name,raw",
        [
            ("search", "fields", "caseName,dateFiled"),
            ("search", "q", '["not", "a", "list"]'),
            ("search", "q", "1984"),
            ("get_endpoint_item", "item_id", "123"),
            ("read_document", "opinion_id", "not-an-integer"),
        ],
    )
    def test_leaves_alone(self, tool, name, raw):
        decoded = MCP_TOOLS[tool].decode_json_arguments({name: raw})
        assert decoded[name] == raw

    @pytest.mark.asyncio
    async def test_run_passes_decoded_arguments(self, monkeypatch):
        tool = MCP_TOOLS["search"]
        seen = {}

        async def fake_call(self, arguments):
            seen.update(arguments)
            return {}

        monkeypatch.setattr(type(tool), "call", fake_call)
        await tool.run({"q": "test", "fields": '["caseName","dateFiled"]'})
        assert seen["fields"] == ["caseName", "dateFiled"]

    def test_deeply_nested_json_left_alone(self):
        raw = "[" * 100_000
        decoded = MCP_TOOLS["search"].decode_json_arguments({"q": raw})
        assert decoded["q"] == raw

    def test_float_text_not_coerced_to_integer(self):
        decoded = MCP_TOOLS["read_document"].decode_json_arguments(
            {"chunk_index": "5.0"}
        )
        assert decoded["chunk_index"] == "5.0"

    @pytest.mark.parametrize(
        "schema,expected",
        [
            ({"type": "number"}, True),
            ({"type": ["integer", "null"]}, False),
            ({"anyOf": [{"type": "integer"}, {"type": "number"}]}, True),
            ({"anyOf": [{"type": "integer"}, {"type": "null"}]}, False),
            ({"oneOf": [{"anyOf": [{"type": "number"}]}]}, True),
            ({}, False),
        ],
    )
    def test_schema_allows_type(self, schema, expected):
        from courtlistener.mcp.tools.mcp_tool import schema_allows_type

        assert schema_allows_type(schema, "number") is expected

    def test_float_text_decoded_where_schema_allows_number(self):
        tool = MCP_TOOLS["read_document"]
        properties = tool.parameters["properties"]
        original = properties["chunk_index"]
        properties["chunk_index"] = {
            "anyOf": [{"type": "integer"}, {"type": "number"}]
        }
        tool.__dict__.pop("property_validators", None)
        try:
            decoded = tool.decode_json_arguments({"chunk_index": "5.0"})
        finally:
            properties["chunk_index"] = original
            tool.__dict__.pop("property_validators", None)
        assert decoded["chunk_index"] == 5.0
