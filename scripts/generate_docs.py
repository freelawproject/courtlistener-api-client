import importlib
import inspect
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from utils import (
    BASE_DIR,
    DOCS_DIR,
    generated_notice,
    schema_type_str,
)

from courtlistener import CourtListener
from courtlistener.models import ENDPOINTS
from courtlistener.sync_client.resource import Resource
from courtlistener.utils import inline_refs

ENDPOINTS_DOCS_DIR = DOCS_DIR / "endpoints"

# Handwritten docs for operations beyond get and list:
# `<doc name>.<operation>.md`, e.g. `docket-alerts.create.md`.
OPERATIONS_DIR = DOCS_DIR / ".src" / "endpoint-operations"

# HTTP methods an operation file may declare, in page order.
METHODS = ("POST", "PATCH", "PUT", "DELETE")

# Handwritten intro for docs/README.md; the endpoint table is appended.
README_SOURCE = DOCS_DIR / ".src" / "README.md"

GENERATED_NOTICE = generated_notice("generate_docs.py")


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


def choices_table(choices: list[dict]) -> list[str]:
    """A choice list as Markdown table lines."""
    rows = ["| Value | Label |", "|---|---|"]
    for choice in choices:
        value = json.dumps(choice.get("value")).replace("|", "\\|")
        label = str(choice.get("display_name", "")).replace("|", "\\|")
        rows.append(f"| `{value}` | {label} |")
    return rows


def slug(heading: str) -> str:
    """GitHub's anchor for a heading's text."""
    text = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return text.replace(" ", "-")


@dataclass
class ChoiceList:
    """One entry in a page's Choices section."""

    heading: str  # e.g. "`court`" or "`alert_type` (create)"
    table: list[str]  # Markdown table lines
    count: int

    @property
    def anchor(self) -> str:
        return slug(self.heading)

    def link(self) -> str:
        return f"[{self.count}](#{self.anchor})"


def field_choices(field: str, prop: dict, label: str = "") -> ChoiceList:
    """A generated field's choices; `label` qualifies the heading."""
    choices = prop["choices"]
    heading = f"`{field}`" + (f" ({label})" if label else "")
    return ChoiceList(heading, choices_table(choices), len(choices))


def cell(text: str) -> str:
    """Escape text for a Markdown table cell."""
    return text.replace("|", "\\|")


def render_fields(
    rows: list[tuple[str, dict, "ChoiceList | None"]], lines: list[str]
) -> None:
    """A field table: name, type, lookups, choices link, and description."""
    if not rows:
        lines.extend(["*No fields.*", ""])
        return
    lines.extend(
        [
            "| Field | Type | Lookups | Choices | Description |",
            "|---|---|---|---|---|",
        ]
    )
    for name, prop, choices in rows:
        scalars, lookups, _ = split_branches(prop)
        type_ = " | ".join(scalars) if scalars else "object"
        lookups_cell = ", ".join(f"`{lookup}`" for lookup in lookups)
        choices_cell = choices.link() if choices is not None else ""
        description = " ".join((prop.get("description") or "").split())
        lines.append(
            f"| `{name}` | {cell(type_)} | {lookups_cell} | {choices_cell} "
            f"| {cell(description)} |"
        )
    lines.append("")


def render_choices_section(
    entries: list[ChoiceList], lines: list[str]
) -> None:
    """Add the page's Choices section: each list collapsed under a heading."""
    if not entries:
        return
    while lines and not lines[-1]:
        lines.pop()
    lines.extend(["", "## Choices", ""])
    for entry in entries:
        lines.extend(
            [
                f"### {entry.heading}",
                "",
                f"<details><summary>{entry.count} choices</summary>",
                "",
                *entry.table,
                "",
                "</details>",
                "",
            ]
        )


def check_anchors(doc: str, lines: list[str]) -> None:
    """Fail if an in-page link's anchor is missing or used by two headings."""
    anchors = [
        slug(line.lstrip("#")) for line in lines if re.match(r"#{1,6} ", line)
    ]
    links = set(re.findall(r"\]\(#([^)]+)\)", "\n".join(lines)))
    repeated = sorted(a for a in links if anchors.count(a) > 1)
    missing = sorted(links - set(anchors))
    if repeated or missing:
        raise RuntimeError(
            f"{doc}.md: repeated anchors {repeated}, "
            f"links to missing anchors {missing}"
        )


def doc_name(model) -> str:
    """The endpoint's doc file name, without `.md`: its endpoint ID."""
    return model.endpoint_id.replace("/", "-")


@dataclass
class Operation:
    """A handwritten operation doc: its name, HTTP method, model and body."""

    name: str
    method: str
    model: type | None
    body: str
    # Operation-specific choice lists, by field: table lines.
    choices: dict[str, list[str]]


def source_link(obj: Any) -> str:
    """A Markdown link from an endpoint page to where `obj` is defined."""
    path = Path(inspect.getsourcefile(obj) or "").resolve()
    line = inspect.getsourcelines(obj)[1]
    href = os.path.relpath(path, ENDPOINTS_DOCS_DIR)
    return f"[`{obj.__qualname__}`]({href}#L{line})"


def parse_operation(path: Path, doc: str) -> Operation:
    """Read an operation file: front matter (method, model), then the body."""
    text = path.read_text()
    meta: dict[str, str] = {}
    if text.startswith("---\n"):
        header, _, text = text[len("---\n") :].partition("\n---\n")
        for line in header.splitlines():
            key, sep, value = line.partition(":")
            if not sep:
                raise RuntimeError(f"{path.name}: bad front matter: {line!r}")
            meta[key.strip()] = value.strip()
    unknown = set(meta) - {"method", "model"}
    if unknown:
        raise RuntimeError(
            f"{path.name}: unknown front matter keys: {sorted(unknown)}"
        )
    method = meta.get("method", "").upper()
    if method not in METHODS:
        raise RuntimeError(
            f"{path.name}: front matter must set `method` to one of "
            + ", ".join(METHODS)
        )
    model = None
    if meta.get("model"):
        module, _, attr = meta["model"].rpartition(".")
        model = getattr(importlib.import_module(module), attr)
    name = path.name[len(doc) + 1 : -len(".md")]
    body, _, choices_text = text.partition("\n## Choices\n")
    choices: dict[str, list[str]] = {}
    field = None
    for line in choices_text.splitlines():
        if line.startswith("### "):
            field = line[len("### ") :].strip().strip("`")
            choices[field] = []
        elif field and line.strip():
            choices[field].append(line.strip())
    return Operation(name, method, model, body.strip(), choices)


def operations(doc: str) -> list[Operation]:
    """An endpoint's handwritten operations, in page order."""
    ops = [
        parse_operation(path, doc)
        for path in OPERATIONS_DIR.glob(f"{doc}.*.md")
    ]
    return sorted(ops, key=lambda op: (METHODS.index(op.method), op.name))


def client_operations(name: str) -> dict[str, Any]:
    """Public methods the client's resource for `name` adds to Resource."""
    resource = getattr(CourtListener(api_token="docs"), name)
    methods: dict[str, Any] = {}
    for cls in type(resource).__mro__:
        if cls is Resource or not issubclass(cls, Resource):
            break
        for attr, value in vars(cls).items():
            if not attr.startswith("_") and callable(value):
                methods.setdefault(attr, value)
    return methods


CHOICES_TOKEN = "(choices)"


def render_operations(
    name: str,
    doc: str,
    lines: list[str],
    entries: list[ChoiceList],
    field_entries: dict[str, ChoiceList],
) -> None:
    """Add a section per HTTP method from the endpoint's operation docs.

    In an operation's body, `(choices)` in a field's table row links to
    that field's choices: the operation's own (from its `## Choices`
    part), else an earlier operation's on the page, else the GET field's.
    """
    methods = client_operations(name)
    earlier: dict[str, ChoiceList] = {}
    current = None
    for op in operations(doc):
        if op.method != current:
            while lines and not lines[-1]:
                lines.pop()
            lines.extend(["", f"## {op.method}", ""])
            current = op.method
        lines.extend([f"### {op.name}", ""])
        if op.model is not None:
            lines.extend([f"Model: {source_link(op.model)}", ""])
        else:
            lines.extend([f"Source: {source_link(methods[op.name])}", ""])

        own = {
            field: ChoiceList(
                f"`{field}` ({op.name})", table, max(len(table) - 2, 0)
            )
            for field, table in op.choices.items()
        }
        entries.extend(own.values())
        body = []
        for line in op.body.splitlines():
            if CHOICES_TOKEN in line:
                match = re.match(r"(?:- |\| )`([^`]+)`", line)
                field = match.group(1) if match else ""
                entry = (
                    own.get(field)
                    or earlier.get(field)
                    or field_entries.get(field)
                )
                if entry is None:
                    raise RuntimeError(
                        f"{doc}.{op.name}.md: no choices for `{field}`; add "
                        "them under `## Choices` in the file"
                    )
                line = line.replace(CHOICES_TOKEN, entry.link())
            body.append(line)
        earlier.update(own)
        if body:
            lines.extend(["\n".join(body), ""])


def check_operations(endpoints: dict) -> None:
    """Fail unless the operation docs match what the client implements."""
    problems = []
    doc_names = {doc_name(model) for model in endpoints.values()}
    for path in sorted(OPERATIONS_DIR.glob("*.md")):
        if (
            path.name != "README.md"
            and path.name.split(".")[0] not in doc_names
        ):
            problems.append(f"{path.name}: matches no endpoint")
    for name, model in endpoints.items():
        doc = doc_name(model)
        documented = {op.name for op in operations(doc)}
        implemented = set(client_operations(name))
        for op in sorted(implemented - documented):
            problems.append(f"client.{name}.{op}: missing {doc}.{op}.md")
        for op in sorted(documented - implemented):
            problems.append(f"{doc}.{op}.md: client.{name} has no `{op}`")
    if problems:
        raise RuntimeError(
            "Endpoint operation docs in "
            f"{OPERATIONS_DIR.relative_to(BASE_DIR)} don't match the "
            "client:\n  " + "\n  ".join(problems)
        )


def field_schemas(model) -> dict[str, dict]:
    """A model's field schemas, with `$ref`s inlined."""
    schema = model.model_json_schema()
    defs = schema.get("$defs", {})
    return {
        name: inline_refs(prop, defs)
        for name, prop in schema.get("properties", {}).items()
    }


def search_types(model) -> list[tuple[str, str, Any]]:
    """The search types as (code, label, per-type model), in API order."""
    by_code = {
        m.model_fields["type"].default: m
        for m in ENDPOINTS.values()
        if m.endpoint_id.endswith("-search") and "type" in m.model_fields
    }
    choices = field_schemas(model)["type"]["choices"]
    return [
        (c["value"], c["display_name"], by_code[c["value"]])
        for c in choices
        if c["value"] in by_code
    ]


def render_search(name: str, model, lines: list[str]) -> None:
    """The search GET section: one field list per search type.

    `SearchEndpoint` merges every type's fields, but each type accepts
    only its own. The per-type sections come from the generated
    per-type models (`OpinionSearchEndpoint` and so on).
    """
    types = search_types(model)
    sections = {code: field_schemas(m) for code, _, m in types}

    # One choice list per field when every type that has it agrees,
    # otherwise one per type.
    entries: dict[tuple[str, str], ChoiceList] = {}
    for code, label, _ in types:
        for field, prop in sections[code].items():
            if field == "type" or not prop.get("choices"):
                continue
            using = [f[field] for f in sections.values() if field in f]
            if all(p.get("choices") == prop["choices"] for p in using):
                entries.setdefault((field, ""), field_choices(field, prop))
            else:
                entries[(field, code)] = field_choices(field, prop, label)

    lines.extend(
        [
            "## GET",
            "",
            f"Model: {source_link(model)}",
            "",
            "```python",
            f'client.{name}.list(type="o", **kwargs)',
            "```",
            "",
            "`type` picks what to search, and each type takes its own fields:",
            "",
        ]
    )
    for code, label, _ in types:
        lines.append(f'- [{label}](#{slug(label)}): `type="{code}"`')
    lines.append("")

    for code, label, type_model in types:
        lines.extend(
            [
                f"### {label}",
                "",
                f'`type="{code}"` · Model: {source_link(type_model)}',
                "",
            ]
        )
        render_fields(
            [
                (
                    field,
                    prop,
                    entries.get((field, code)) or entries.get((field, "")),
                )
                for field, prop in sections[code].items()
                if field != "type"
            ],
            lines,
        )

    render_choices_section(list(entries.values()), lines)


def render_markdown(name: str, model) -> str:
    description = (model.model_json_schema().get("description") or "").strip()
    # Generated models describe themselves as "<Name> Endpoint", which
    # says nothing the heading doesn't.
    if description.removesuffix(" Endpoint").strip() == model.endpoint_name:
        description = ""

    lines = [
        GENERATED_NOTICE,
        "",
        f"# {model.endpoint.strip('/')}",
        "",
    ]
    if description:
        lines.append(description)
        lines.append("")

    if name == "search":
        render_search(name, model, lines)
    else:
        render_endpoint(name, model, lines)
    check_anchors(doc_name(model), lines)
    return "\n".join(lines).rstrip() + "\n"


def render_endpoint(name: str, model, lines: list[str]) -> None:
    """A standard endpoint: GET fields, other operations, then choices."""
    lines.extend(
        [
            "## GET",
            "",
            f"Model: {source_link(model)}",
            "",
            "```python",
            f"client.{name}.get(item_id)",
            f"client.{name}.list(**kwargs)",
            "```",
            "",
        ]
    )
    fields = field_schemas(model)
    field_entries = {
        field: field_choices(field, prop)
        for field, prop in fields.items()
        if prop.get("choices")
    }
    render_fields(
        [
            (field, prop, field_entries.get(field))
            for field, prop in fields.items()
        ],
        lines,
    )

    entries = list(field_entries.values())
    render_operations(name, doc_name(model), lines, entries, field_entries)
    render_choices_section(entries, lines)


def render_readme(endpoints: dict) -> str:
    """docs/README.md: the handwritten intro plus a generated endpoint table."""
    lines = [GENERATED_NOTICE, "", README_SOURCE.read_text().strip(), ""]
    lines.extend(
        [
            "| Endpoint | Client attribute | Operations |",
            "|---|---|---|",
        ]
    )
    for name, model in sorted(
        endpoints.items(), key=lambda item: item[1].endpoint
    ):
        doc = doc_name(model)
        # Search results have no detail view, so search has no `get`.
        reads = ["list"] if name == "search" else ["get", "list"]
        names = reads + [op.name for op in operations(doc)]
        listed = ", ".join(f"`{op}`" for op in names)
        lines.append(
            f"| [`{model.endpoint.strip('/')}`](./endpoints/{doc}.md) "
            f"| `client.{name}` | {listed} |"
        )
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
    check_operations(endpoints)

    expected_files = set()
    for name, model in endpoints.items():
        md_path = ENDPOINTS_DOCS_DIR / f"{doc_name(model)}.md"
        md_path.write_text(render_markdown(name, model))
        expected_files.add(md_path.name)

    (DOCS_DIR / "README.md").write_text(render_readme(endpoints))

    check_stale_files(expected_files)
    print(
        f"Documented {len(endpoints)} endpoints in "
        f"{ENDPOINTS_DOCS_DIR.relative_to(BASE_DIR)}"
    )


if __name__ == "__main__":
    main()
