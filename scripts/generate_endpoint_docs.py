import json

from utils import (
    BASE_DIR,
    DOCS_DIR,
    generated_notice,
    property_constraints,
    schema_type_str,
)

from courtlistener.mcp.tools.utils import inline_refs
from courtlistener.models import ENDPOINTS

ENDPOINTS_DOCS_DIR = DOCS_DIR / "endpoints"

GENERATED_NOTICE = generated_notice("generate_endpoint_docs.py")

CHOICES_COLLAPSE_THRESHOLD = 10


def documented_endpoints() -> dict:
    """Endpoint models to document, keyed by client attribute name."""
    return {
        name: model
        for name, model in ENDPOINTS.items()
        if not model.endpoint_id.endswith("-search")
    }


def split_branches(prop: dict) -> tuple[list[str], list[str], bool]:
    """Partition a field's anyOf branches for display.

    Returns (scalar type strings, filter lookup operators, whether the
    field accepts a related-object dict). The implicit null branch is
    dropped — every endpoint field is optional.
    """
    branches = prop.get("anyOf") or [prop]
    scalars: list[str] = []
    lookups: list[str] = []
    related_dict = False
    for branch in branches:
        if branch.get("type") == "null":
            continue
        if branch.get("type") == "object":
            if branch.get("properties"):
                lookups = sorted(branch["properties"])
            else:
                related_dict = True
        else:
            scalars.append(schema_type_str(branch))
    return scalars, lookups, related_dict


def render_choices(choices: list[dict], lines: list[str]) -> None:
    table = [
        "| Value | Label |",
        "|---|---|",
    ]
    for choice in choices:
        value = json.dumps(choice.get("value")).replace("|", "\\|")
        label = str(choice.get("display_name", "")).replace("|", "\\|")
        table.append(f"| `{value}` | {label} |")

    if len(choices) > CHOICES_COLLAPSE_THRESHOLD:
        lines.append(f"<details><summary>Choices ({len(choices)})</summary>")
        lines.append("")
        lines.extend(table)
        lines.append("")
        lines.append("</details>")
    else:
        lines.append(f"Choices ({len(choices)}):")
        lines.append("")
        lines.extend(table)
    lines.append("")


def render_field(
    name: str,
    prop: dict,
    related_targets: dict[str, str],
    lines: list[str],
) -> None:
    lines.append(f"### `{name}`")
    lines.append("")

    scalars, lookups, related_dict = split_branches(prop)
    badges = [" | ".join(scalars) if scalars else "object"]
    badges.extend(property_constraints(prop))
    lines.append(" · ".join(badges))
    lines.append("")

    description = (prop.get("description") or "").strip()
    if description:
        lines.append(description)
        lines.append("")

    if lookups:
        lines.append(
            "Lookups: " + ", ".join(f"`{lookup}`" for lookup in lookups)
        )
        lines.append("")

    related_class = prop.get("related_class_name")
    if related_class or related_dict:
        target = related_targets.get(related_class)
        if target:
            note = f"Related endpoint: [`{target}`](./{target}.md)"
        else:
            note = "Accepts related-object lookups as a dict."
        lines.append(note)
        lines.append("")

    choices = prop.get("choices")
    if choices:
        render_choices(choices, lines)


def render_markdown(name: str, model, related_targets: dict[str, str]) -> str:
    schema = model.model_json_schema()
    defs = schema.get("$defs", {})
    properties = schema.get("properties", {})
    description = (schema.get("description") or "").strip()
    source = model.__module__.replace(".", "/") + ".py"

    lines = [
        GENERATED_NOTICE,
        "",
        f"# `{name}`",
        "",
    ]
    title = getattr(model, "endpoint_name", None)
    if title and title != name:
        lines.append(f"**{title}**")
        lines.append("")

    lines.append(f"- **Path:** `{model.endpoint}`")
    lines.append(f"- **Endpoint ID:** `{model.endpoint_id}`")
    lines.append(f"- **Source:** `{source}`")
    lines.append(f"- **Fields:** {len(properties)}")
    lines.append("")

    if description:
        lines.append("## Description")
        lines.append("")
        lines.append(description)
        lines.append("")

    lines.append("## Fields")
    lines.append("")
    if properties:
        for prop_name, prop in properties.items():
            render_field(
                prop_name, inline_refs(prop, defs), related_targets, lines
            )
    else:
        lines.append("*No fields.*")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_readme(endpoint_names: list[str]) -> str:
    lines = [
        GENERATED_NOTICE,
        "",
        "# API Endpoints",
        "",
    ]
    lines.extend(f"- [`{name}`](./{name}.md)" for name in endpoint_names)
    return "\n".join(lines) + "\n"


def check_stale_files(expected: set[str]) -> None:
    stale = [
        path.name
        for path in ENDPOINTS_DOCS_DIR.glob("*.md")
        if path.name not in expected
    ]
    if stale:
        raise RuntimeError(
            "Stale endpoint docs found (no matching endpoint model): "
            + ", ".join(sorted(stale))
            + ". Delete them if the endpoint was removed or renamed."
        )


def main() -> None:
    ENDPOINTS_DOCS_DIR.mkdir(parents=True, exist_ok=True)

    endpoints = documented_endpoints()
    related_targets = {
        model.__name__: name for name, model in endpoints.items()
    }

    expected_files = set()
    for name, model in endpoints.items():
        md_path = ENDPOINTS_DOCS_DIR / f"{name}.md"
        md_path.write_text(render_markdown(name, model, related_targets))
        expected_files.add(md_path.name)

    readme_path = ENDPOINTS_DOCS_DIR / "README.md"
    readme_path.write_text(render_readme(list(endpoints)))
    expected_files.add(readme_path.name)

    check_stale_files(expected_files)
    print(
        f"Documented {len(endpoints)} endpoints in "
        f"{ENDPOINTS_DOCS_DIR.relative_to(BASE_DIR)}"
    )


if __name__ == "__main__":
    main()
