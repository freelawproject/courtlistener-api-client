import json
from typing import Any

import tiktoken
from utils import (
    BASE_DIR,
    DOCS_DIR,
    generated_notice,
    property_constraints,
    schema_type_str,
)

from courtlistener.mcp.tools import MCP_TOOLS

TOOLS_DOCS_DIR = DOCS_DIR / "mcp_tools"

ENCODING = tiktoken.get_encoding("cl100k_base")

GENERATED_NOTICE = generated_notice("generate_mcp_tool_docs.py")

STANDARD_SCHEMA_KEYS = {
    "$defs",
    "$ref",
    "additionalProperties",
    "allOf",
    "anyOf",
    "const",
    "default",
    "description",
    "enum",
    "examples",
    "exclusiveMaximum",
    "exclusiveMinimum",
    "format",
    "items",
    "maxItems",
    "maxLength",
    "maximum",
    "minItems",
    "minLength",
    "minimum",
    "multipleOf",
    "oneOf",
    "pattern",
    "properties",
    "required",
    "title",
    "type",
    "uniqueItems",
}


def count_tokens(text: str) -> int:
    return len(ENCODING.encode(text))


def dump_json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def fence_json_chunks(description: str) -> str:
    """Wrap JSON blocks embedded in a description in markdown code fences."""
    chunks = []
    for chunk in description.split("\n\n"):
        stripped = chunk.strip()
        if stripped.startswith(("[", "{")):
            try:
                json.loads(stripped)
            except ValueError:
                pass
            else:
                chunk = f"```json\n{stripped}\n```"
        chunks.append(chunk)
    return "\n\n".join(chunks)


def nonstandard_keys(schema: Any) -> set[str]:
    """Recursively find non-JSON-Schema keys in a property schema tree."""
    found = set()
    if isinstance(schema, dict):
        found.update(set(schema) - STANDARD_SCHEMA_KEYS)
        for key in ("items", "additionalProperties"):
            found.update(nonstandard_keys(schema.get(key)))
        for key in ("anyOf", "oneOf", "allOf"):
            for option in schema.get(key, []):
                found.update(nonstandard_keys(option))
        for nested in schema.get("properties", {}).values():
            found.update(nonstandard_keys(nested))
        for nested in schema.get("$defs", {}).values():
            found.update(nonstandard_keys(nested))
    return found


def is_complex(schema: dict) -> bool:
    """Whether a property schema has structure worth showing as raw JSON."""
    return bool(
        schema.get("properties")
        or schema.get("$defs")
        or isinstance(schema.get("items"), dict)
        and schema["items"].get("properties")
    )


def render_property(
    name: str, schema: dict, required: bool, lines: list[str]
) -> None:
    lines.append(f"### `{name}`")
    lines.append("")
    badges = [schema_type_str(schema)]
    badges.append("**required**" if required else "optional")
    badges.extend(property_constraints(schema))
    lines.append(" · ".join(badges))
    lines.append("")
    description = schema.get("description", "").strip()
    if description:
        lines.append(fence_json_chunks(description))
        lines.append("")
    extra_keys = nonstandard_keys(schema)
    if extra_keys:
        lines.append(
            "Non-standard schema keys: "
            + ", ".join(f"`{key}`" for key in sorted(extra_keys))
        )
        lines.append("")
    if is_complex(schema):
        lines.append("<details><summary>Full schema</summary>")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(schema, indent=2, ensure_ascii=False))
        lines.append("```")
        lines.append("")
        lines.append("</details>")
        lines.append("")


def render_markdown(name: str, tool_entry: dict, source: str) -> str:
    input_schema = tool_entry["inputSchema"]
    description = (tool_entry.get("description") or "").strip()
    annotations = tool_entry.get("annotations") or {}
    properties = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))

    definition_tokens = count_tokens(
        json.dumps(tool_entry, ensure_ascii=False)
    )
    description_tokens = count_tokens(description)
    schema_tokens = count_tokens(json.dumps(input_schema, ensure_ascii=False))

    lines = [
        GENERATED_NOTICE,
        "",
        f"# `{name}`",
        "",
    ]
    title = annotations.get("title") or tool_entry.get("title")
    if title and title != name:
        lines.append(f"**{title}**")
        lines.append("")

    lines.append(f"- **Source:** `{source}`")
    lines.append(
        f"- **Estimated definition size:** ~{definition_tokens} tokens "
        f"(description ~{description_tokens}, input schema ~{schema_tokens}; "
        "cl100k_base)"
    )
    lines.append(
        f"- **Parameters:** {len(properties)} ({len(required)} required)"
    )
    lines.append(
        f"- **Raw input schema:** [`{name}.inputs.json`](./{name}.inputs.json)"
    )
    lines.append("")

    lines.append("## Description")
    lines.append("")
    lines.append(description or "*No description.*")
    lines.append("")

    lines.append("## Annotations")
    lines.append("")
    if annotations:
        lines.append("| Annotation | Value |")
        lines.append("|---|---|")
        for key, value in annotations.items():
            lines.append(f"| `{key}` | `{json.dumps(value)}` |")
    else:
        lines.append("*No annotations.*")
    lines.append("")

    lines.append("## Parameters")
    lines.append("")
    if properties:
        for prop_name, prop_schema in properties.items():
            render_property(
                prop_name, prop_schema, prop_name in required, lines
            )
    else:
        lines.append("*No parameters.*")
        lines.append("")

    schema_extra_keys = nonstandard_keys(input_schema)
    if schema_extra_keys:
        lines.append("## Schema warnings")
        lines.append("")
        lines.append(
            "The input schema contains non-standard JSON Schema keys, "
            "which strict clients may reject: "
            + ", ".join(f"`{key}`" for key in sorted(schema_extra_keys))
        )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_readme(tool_names: list[str]) -> str:
    lines = [
        GENERATED_NOTICE,
        "",
        "# MCP Tools",
        "",
    ]
    lines.extend(f"- [`{name}`](./{name}.md)" for name in tool_names)
    return "\n".join(lines) + "\n"


def check_stale_files(expected: set[str]) -> None:
    stale = [
        path.name
        for pattern in ("*.md", "*.inputs.json")
        for path in TOOLS_DOCS_DIR.glob(pattern)
        if path.name not in expected
    ]
    if stale:
        raise RuntimeError(
            "Stale tool docs found (no matching tool in the registry): "
            + ", ".join(sorted(stale))
            + ". Delete them if the tool was removed or renamed."
        )


def main() -> None:
    TOOLS_DOCS_DIR.mkdir(parents=True, exist_ok=True)

    expected_files = set()
    for name, mcp_tool in MCP_TOOLS.items():
        tool_entry = (
            mcp_tool.get_tool()
            .to_mcp_tool()
            .model_dump(by_alias=True, exclude_none=True, mode="json")
        )
        source = mcp_tool.__class__.__module__.replace(".", "/") + ".py"

        json_path = TOOLS_DOCS_DIR / f"{name}.inputs.json"
        md_path = TOOLS_DOCS_DIR / f"{name}.md"
        json_path.write_text(dump_json(tool_entry["inputSchema"]))
        md_path.write_text(render_markdown(name, tool_entry, source))
        expected_files.update({json_path.name, md_path.name})

        extra_keys = nonstandard_keys(tool_entry["inputSchema"])
        if extra_keys:
            print(
                f"WARNING: {name} input schema contains non-standard "
                "JSON Schema keys: " + ", ".join(sorted(extra_keys))
            )

    readme_path = TOOLS_DOCS_DIR / "README.md"
    readme_path.write_text(render_readme(list(MCP_TOOLS)))
    expected_files.add(readme_path.name)

    check_stale_files(expected_files)
    print(
        f"Documented {len(MCP_TOOLS)} tools in "
        f"{TOOLS_DOCS_DIR.relative_to(BASE_DIR)}"
    )


if __name__ == "__main__":
    main()
