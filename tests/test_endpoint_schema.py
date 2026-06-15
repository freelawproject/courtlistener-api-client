"""Tests for get_endpoint_schema output and $ref inlining."""

from __future__ import annotations

import asyncio
import json

from courtlistener.mcp.tools import MCP_TOOLS
from courtlistener.mcp.tools.utils import inline_refs
from courtlistener.models import ENDPOINTS


def _schema(endpoint_id: str) -> dict:
    tool = MCP_TOOLS["get_endpoint_schema"]
    return asyncio.run(tool({"endpoint_id": endpoint_id}, None))


def _non_search_endpoint_ids() -> list[str]:
    ids: list[str] = []
    for endpoint in ENDPOINTS.values():
        eid = endpoint.endpoint_id
        if eid == "search" or eid.endswith("-search"):
            continue
        if eid not in ids:
            ids.append(eid)
    return ids


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


class TestEndpointSchemaOutput:
    def test_no_dangling_refs_anywhere(self):
        """No endpoint schema may contain a $ref key or a #/$defs pointer."""
        for eid in _non_search_endpoint_ids():
            payload = json.dumps(_schema(eid))
            assert '"$ref"' not in payload, f"{eid} has a $ref key"
            assert "#/$defs" not in payload, (
                f"{eid} has a dangling $defs pointer"
            )

    def test_filter_lookups_are_inlined(self):
        """A string field should carry its lookup operators inline."""
        schema = _schema("courts")
        full_name = schema["properties"]["full_name"]
        branches = full_name["anyOf"]
        filter_branch = next(b for b in branches if b.get("type") == "object")
        assert "contains" in filter_branch["properties"]
        assert "startswith" in filter_branch["properties"]

    def test_schema_noise_is_stripped(self):
        """Inlined defs must not carry title/default/related_class_name."""
        schema = _schema("courts")

        def has_noise(node) -> bool:
            if isinstance(node, dict):
                if {"title", "default", "related_class_name"} & node.keys():
                    return True
                return any(has_noise(v) for v in node.values())
            if isinstance(node, list):
                return any(has_noise(v) for v in node)
            return False

        for field_schema in schema["properties"].values():
            assert not has_noise(field_schema)

    def test_legitimate_title_field_is_preserved(self):
        """A real column named 'title' must survive (not stripped as noise)."""
        schema = _schema("fjc-integrated-database")
        assert "title" in schema["properties"]
