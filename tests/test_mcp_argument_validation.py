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

from unittest.mock import MagicMock, patch

import pytest
from fastmcp.exceptions import ToolError
from jsonschema import Draft202012Validator

from courtlistener.mcp.exceptions import ToolArgumentValidationError
from courtlistener.mcp.tools import MCP_TOOLS
from courtlistener.mcp.tools.mcp_tool import coerce_integral_floats
from courtlistener.mcp.tools.read_document_tool import ReadDocumentTool
from courtlistener.mcp.tools.utils import endpoint_ids
from courtlistener.models import ENDPOINTS
from courtlistener.utils import did_you_mean, validate_model_fields

ENDPOINT_ID_TOOLS = [
    "get_endpoint_schema",
    "get_endpoint_item",
    "call_endpoint",
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

    @pytest.mark.parametrize("name", ENDPOINT_ID_TOOLS)
    def test_search_is_never_an_endpoint_id(self, name):
        enum = MCP_TOOLS[name].get_input_schema()["properties"]["endpoint_id"][
            "enum"
        ]
        assert "search" not in enum
        assert not [e for e in enum if e.endswith("-search")]

    def test_call_endpoint_query_stays_open(self):
        """`query` is free-form; Pydantic validates its contents."""
        schema = MCP_TOOLS["call_endpoint"].get_input_schema()
        assert schema["properties"]["query"]["additionalProperties"] is True

    def test_endpoint_ids_exclude_search(self):
        assert "search" not in endpoint_ids()
        assert "opinion-search" not in endpoint_ids()


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

    @pytest.mark.parametrize("name", ENDPOINT_ID_TOOLS)
    def test_endpoint_id_description_points_at_the_search_tool(self, name):
        prop = MCP_TOOLS[name].get_input_schema()["properties"]["endpoint_id"]
        assert "use the `search` tool" in prop["description"]

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

    @pytest.mark.parametrize(
        "raw,expected", [("5.0", 5), ("[1.0, 2]", [1, 2]), ("5.5", "5.5")]
    )
    def test_float_text_decoded_to_integer(self, raw, expected):
        decoded = MCP_TOOLS["read_document"].decode_json_arguments(
            {"chunk_index": raw}
        )
        assert decoded["chunk_index"] == expected
        assert type(decoded["chunk_index"]) is type(expected)

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


class TestIntegralFloatArguments:
    """jsonschema accepts ``1.0`` as an integer (issue #322)."""

    @pytest.mark.parametrize(
        "tool,name,value,expected",
        [
            ("read_document", "opinion_id", 217512.0, 217512),
            ("read_document", "chunk_index", 1.0, 1),
            ("read_document", "chunk_index", [1.0, 2.0], [1, 2]),
            ("search_document", "opinion_id", [15.0, 85], [15, 85]),
            ("search", "cited_gt", 10.0, 10),
            ("get_endpoint_item", "item_id", 5.0, 5),
        ],
    )
    def test_coerces(self, tool, name, value, expected):
        coerced = MCP_TOOLS[tool].coerce_integral_float_arguments(
            {name: value}
        )
        assert coerced[name] == expected
        assert repr(coerced[name]) == repr(expected)

    @pytest.mark.parametrize(
        "name,value,expected",
        [
            ("opinion_id", 1.5, 1.5),
            ("chunk_index", [1.0, 2.5], [1, 2.5]),
            ("opinion_id", True, True),
            ("opinion_id", "7.0", "7.0"),
        ],
    )
    def test_leaves_alone(self, name, value, expected):
        coerced = MCP_TOOLS["read_document"].coerce_integral_float_arguments(
            {name: value}
        )
        assert repr(coerced[name]) == repr(expected)

    def test_non_integral_float_still_rejected(self):
        tool = MCP_TOOLS["read_document"]
        arguments = tool.coerce_integral_float_arguments({"opinion_id": 1.5})
        with pytest.raises(ToolError, match="opinion_id"):
            tool.validate_arguments(arguments)

    @pytest.mark.parametrize(
        "schema",
        [
            {"type": "number"},
            {"anyOf": [{"type": "integer"}, {"type": "number"}]},
            {"type": "string"},
            {},
        ],
    )
    def test_non_integer_schemas_untouched(self, schema):
        assert repr(coerce_integral_floats(5.0, schema)) == "5.0"

    def test_free_form_objects_untouched(self):
        coerced = MCP_TOOLS["call_endpoint"].coerce_integral_float_arguments(
            {"query": {"id": 5.0}}
        )
        assert repr(coerced["query"]["id"]) == "5.0"

    @pytest.mark.asyncio
    async def test_run_passes_coerced_arguments(self, monkeypatch):
        tool = MCP_TOOLS["read_document"]
        seen = {}

        async def fake_call(self, arguments):
            seen.update(arguments)
            return {}

        monkeypatch.setattr(type(tool), "call", fake_call)
        await tool.run({"opinion_id": 217512.0, "chunk_index": "[1.0, 2]"})
        assert repr(seen) == repr(
            {"opinion_id": 217512, "chunk_index": [1, 2]}
        )

    @pytest.mark.asyncio
    async def test_read_document_slices_float_chunk_indexes(self):
        tool = ReadDocumentTool()

        async def fake_fetch(doc_type, doc_id, client):
            assert doc_id == 217512 and type(doc_id) is int
            return "a" * 100 + "b" * 100 + "c" * 50

        client = MagicMock()
        client.__aenter__.return_value = client
        with (
            patch.object(ReadDocumentTool, "get_client", return_value=client),
            patch(
                "courtlistener.mcp.tools.read_document_tool."
                "fetch_document_text",
                fake_fetch,
            ),
        ):
            result = await tool.run(
                {
                    "opinion_id": 217512.0,
                    "chunk_index": [1.0, 2.0, 99],
                    "chunk_size": 100.0,
                }
            )
        text = result.content[0].text
        assert '"text": "' + "b" * 100 + '"' in text
        assert '"text": "' + "c" * 50 + '"' in text
        assert "chunk_index 99 is past the end" in text
