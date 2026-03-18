"""Shared utilities for citation MCP tools."""

from __future__ import annotations

from eyecite.models import (
    CitationBase,
    FullCaseCitation,
    FullLawCitation,
    IdCitation,
    Resource,
    ShortCaseCitation,
    SupraCitation,
    UnknownCitation,
)

# Delimiter used between citations in the compact string sent to the
# citation-lookup API.  Semicolon-space is a natural Bluebook list
# separator that eyecite reliably parses without cleanup.
CITATION_DELIMITER = "; "


def citation_type_label(cite: CitationBase) -> str:
    """Human-readable label for a citation type."""
    labels = {
        FullCaseCitation: "full",
        ShortCaseCitation: "short",
        IdCitation: "id.",
        SupraCitation: "supra",
        FullLawCitation: "statute",
        UnknownCitation: "unknown",
    }
    return labels.get(type(cite), type(cite).__name__)


def format_case_name(cite: FullCaseCitation) -> str:
    """Build a short case name from metadata, if available."""
    meta = cite.metadata
    if meta.plaintiff and meta.defendant:
        return f"{meta.plaintiff} v. {meta.defendant}"
    return ""


def canonical_key(cite: FullCaseCitation) -> str:
    """Canonical key for deduplication: 'volume reporter page'."""
    g = cite.groups
    return f"{g['volume']} {g['reporter']} {g['page']}"


def format_flat_citations(cites: list[CitationBase]) -> str:
    """Format a flat list of citations (no resolution)."""
    if not cites:
        return "No citations found."
    lines = [f"Found {len(cites)} citation(s):\n"]
    for i, cite in enumerate(cites, 1):
        label = citation_type_label(cite)
        text = cite.matched_text()
        lines.append(f'  {i}. [{label}] "{text}"')
    return "\n".join(lines)


def format_resolved_citations(
    cites: list[CitationBase],
    resolutions: dict[Resource, list[CitationBase]],
) -> str:
    """Format citations grouped by resolved resource."""
    cases: list[tuple[Resource, list[CitationBase]]] = []
    statutes: list[tuple[Resource, list[CitationBase]]] = []

    for resource, cite_list in resolutions.items():
        primary = resource.citation
        if isinstance(primary, FullCaseCitation):
            cases.append((resource, cite_list))
        elif isinstance(primary, FullLawCitation):
            statutes.append((resource, cite_list))

    # Find unresolved citations (not in any resource)
    resolved_ids = set()
    for cite_list in resolutions.values():
        for c in cite_list:
            resolved_ids.add(id(c))
    unresolved = [c for c in cites if id(c) not in resolved_ids]

    total = len(cites)
    parts = []
    summary_parts = []
    if cases:
        summary_parts.append(f"{len(cases)} unique case(s)")
    if statutes:
        summary_parts.append(f"{len(statutes)} statute(s)")
    if unresolved:
        summary_parts.append(f"{len(unresolved)} unresolved")

    parts.append(
        f"Found {total} citation(s) referencing "
        + ", ".join(summary_parts)
        + ".\n"
    )

    if cases:
        parts.append("Cases:")
        for i, (resource, cite_list) in enumerate(cases, 1):
            primary = resource.citation
            key = canonical_key(primary)
            name = format_case_name(primary)
            year = primary.metadata.year or ""
            header = f"  {i}. {key}"
            if name:
                header += f" ({name}"
                if year:
                    header += f", {year}"
                header += ")"
            elif year:
                header += f" ({year})"
            header += f" — {len(cite_list)} reference(s)"
            parts.append(header)
            for c in cite_list:
                label = citation_type_label(c)
                parts.append(f'       [{label}] "{c.matched_text()}"')

    if statutes:
        parts.append("\nStatutes:")
        for i, (resource, cite_list) in enumerate(statutes, 1):
            primary = resource.citation
            parts.append(
                f'  {i}. "{primary.matched_text()}" '
                f"— {len(cite_list)} reference(s)"
            )
            for c in cite_list:
                if c is not primary:
                    label = citation_type_label(c)
                    parts.append(f'       [{label}] "{c.matched_text()}"')

    if unresolved:
        parts.append("\nUnresolved:")
        for i, c in enumerate(unresolved, 1):
            label = citation_type_label(c)
            parts.append(f'  {i}. [{label}] "{c.matched_text()}"')

    return "\n".join(parts)


def build_compact_string(unique_citations: list[str]) -> str:
    """Join unique citation strings with our delimiter for the API.

    Uses ``'; '`` (semicolon-space) which is the standard Bluebook
    citation list separator and is parsed reliably by eyecite.
    """
    return CITATION_DELIMITER.join(unique_citations)


def extract_unique_case_citations(
    resolutions: dict[Resource, list[CitationBase]],
) -> list[str]:
    """Get deduplicated canonical citation strings for all case resources."""
    unique: list[str] = []
    seen: set[str] = set()
    for resource in resolutions:
        primary = resource.citation
        if isinstance(primary, FullCaseCitation):
            key = canonical_key(primary)
            if key not in seen:
                seen.add(key)
                unique.append(key)
    return unique


def summarize_cluster(cluster: dict) -> dict:
    """Extract useful fields from a CourtListener cluster object."""
    return {
        "cluster_id": cluster.get("id"),
        "case_name": cluster.get("case_name"),
        "case_name_short": cluster.get("case_name_short"),
        "date_filed": cluster.get("date_filed"),
        "citation_count": cluster.get("citation_count"),
        "precedential_status": cluster.get("precedential_status"),
        "absolute_url": cluster.get("absolute_url"),
        "docket_id": cluster.get("docket"),
        "citations": [
            f"{c['volume']} {c['reporter']} {c['page']}"
            for c in cluster.get("citations", [])
            if c.get("volume") and c.get("reporter") and c.get("page")
        ],
    }


def next_analysis_id(session: dict) -> int:
    """Get the next auto-incrementing analysis ID."""
    analyses = session.get("citation_analyses", {})
    if not analyses:
        return 1
    return max(analyses.keys()) + 1


def format_verification_result(
    citation_key: str,
    result: dict,
    ref_count: int,
    ref_breakdown: str,
    index: int,
) -> str:
    """Format a single verified citation for display."""
    status = result.get("status")
    if status == 200:
        clusters = result.get("clusters", [])
        if not clusters:
            return (
                f"  {index}. {citation_key}\n"
                f"     Status: FOUND (no cluster details)\n"
                f"     References in document: {ref_count} ({ref_breakdown})"
            )
        cluster = clusters[0]
        name = cluster.get("case_name", "Unknown")
        date = cluster.get("date_filed", "")
        cite_count = cluster.get("citation_count", 0)
        url = cluster.get("absolute_url", "")
        parallel = cluster.get("citations", [])

        lines = [f"  {index}. {citation_key} — {name}"]
        if date:
            lines[0] += f" ({date})"
        lines.append(f"     Status: FOUND (cited by {cite_count} opinion(s))")
        lines.append(
            f"     References in document: {ref_count} ({ref_breakdown})"
        )
        if url:
            lines.append(f"     URL: https://www.courtlistener.com{url}")
        if parallel:
            lines.append(f"     Parallel citations: {', '.join(parallel)}")
        return "\n".join(lines)

    elif status == 404:
        return (
            f"  {index}. {citation_key}\n"
            f"     Status: NOT FOUND — may be incorrect or not in CourtListener\n"
            f"     References in document: {ref_count} ({ref_breakdown})"
        )
    elif status == 300:
        clusters = result.get("clusters", [])
        names = [c.get("case_name", "?") for c in clusters[:3]]
        return (
            f"  {index}. {citation_key}\n"
            f"     Status: AMBIGUOUS — matches {len(clusters)} cases: "
            + ", ".join(names)
            + "\n"
            f"     References in document: {ref_count} ({ref_breakdown})"
        )
    elif status == 400:
        return (
            f"  {index}. {citation_key}\n"
            f"     Status: INVALID — could not be parsed by the API\n"
            f"     References in document: {ref_count} ({ref_breakdown})"
        )
    else:
        return (
            f"  {index}. {citation_key}\n"
            f"     Status: {status}\n"
            f"     References in document: {ref_count} ({ref_breakdown})"
        )


def build_ref_breakdown(
    cite_list: list[CitationBase],
) -> tuple[int, str]:
    """Count references by type and return (total, breakdown_string)."""
    counts: dict[str, int] = {}
    for c in cite_list:
        label = citation_type_label(c)
        counts[label] = counts.get(label, 0) + 1
    total = sum(counts.values())
    parts = [f"{v} {k}" for k, v in counts.items()]
    return total, ", ".join(parts)
