"""Shared utilities for citation MCP tools."""

from __future__ import annotations

from eyecite.models import (
    CitationBase,
    FullCaseCitation,
    FullCitation,
    FullLawCitation,
    IdCitation,
    ShortCaseCitation,
    SupraCitation,
    UnknownCitation,
)
from eyecite.models import (
    Resource as CitationResource,
)

# Delimiter used between citations in the compact string sent to the
# citation-lookup API.  Semicolon-space is a natural Bluebook list
# separator that eyecite reliably parses without cleanup.
CITATION_DELIMITER = "; "

# Maximum citations per API request before 429 throttling.
MAX_CITATIONS_PER_REQUEST = 250


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


def canonical_key(cite: FullCitation) -> str:
    """Canonical key for deduplication: 'volume reporter page'."""
    g = cite.groups
    return f"{g['volume']} {g['reporter']} {g['page']}"


def format_resolved_citations(
    cites: list[CitationBase],
    resolutions: dict[CitationResource, list[CitationBase]],
) -> str:
    """Format citations grouped by resolved resource."""
    cases: list[tuple[CitationResource, list[CitationBase]]] = []
    statutes: list[tuple[CitationResource, list[CitationBase]]] = []

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
            meta = primary.metadata
            name = ""
            if meta.plaintiff and meta.defendant:
                name = f"{meta.plaintiff} v. {meta.defendant}"
            year = meta.year or ""
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
    """Join unique citation strings with our delimiter for the API."""
    return CITATION_DELIMITER.join(unique_citations)


def process_api_results(
    results: list[dict],
    batch: list[str],
    verified: dict[str, dict],
    pending: list[str],
) -> None:
    """Process API results, updating verified and pending dicts.

    Each API result is matched back to the batch citation it belongs
    to by comparing the citation text. Results with status 429 are
    left in pending for later retry.
    """
    for result in results:
        citation_text = result.get("citation", "")
        status = result.get("status")

        # Match this result to a batch citation
        matched_key = None
        if citation_text in batch:
            matched_key = citation_text
        else:
            normalized = citation_text.strip().lower()
            for key in batch:
                if key.strip().lower() == normalized:
                    matched_key = key
                    break

        if matched_key is None:
            continue

        if status == 429:
            # Rate-limited — leave in pending
            continue

        # Summarize clusters to reduce stored data
        clusters = [
            {
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
            for cluster in result.get("clusters", [])
        ]

        verified[matched_key] = {
            "status": status,
            "citation": citation_text,
            "clusters": clusters,
            "error_message": result.get("error_message"),
        }
        if matched_key in pending:
            pending.remove(matched_key)


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


def format_analysis(
    analysis_id: int,
    cites: list[CitationBase],
    resolutions: dict[CitationResource, list[CitationBase]],
    resource_refs: dict[str, dict],
    unique_citations: list[str],
    verified: dict[str, dict],
    pending: list[str],
) -> str:
    """Format the full analysis output."""
    # Count by type
    case_count = sum(
        1 for r in resolutions if isinstance(r.citation, FullCaseCitation)
    )
    statute_count = sum(
        1 for r in resolutions if not isinstance(r.citation, FullCaseCitation)
    )
    # Find unresolved
    resolved_ids = set()
    for cite_list in resolutions.values():
        for c in cite_list:
            resolved_ids.add(id(c))
    unresolved = [c for c in cites if id(c) not in resolved_ids]

    parts = [f"Citation Analysis (Job ID: {analysis_id})\n"]

    # Summary line
    extraction_parts = [f"{len(cites)} citation(s) found"]
    if case_count:
        extraction_parts.append(f"{case_count} unique case(s)")
    if statute_count:
        extraction_parts.append(f"{statute_count} statute(s)")
    if unresolved:
        extraction_parts.append(f"{len(unresolved)} unresolved")
    parts.append("Extraction: " + ", ".join(extraction_parts) + ".")

    verified_count = len(verified)
    total_unique = len(unique_citations)
    pending_count = len(pending)
    verification_line = (
        f"Verification: {verified_count} of {total_unique} verified."
    )
    if pending_count:
        verification_line += (
            f" ({pending_count} pending — use resume_citation_analysis "
            f"with job_id={analysis_id})"
        )
    parts.append(verification_line)

    # Verified cases
    if verified or pending:
        parts.append("\nCases:")
        idx = 1
        for key in unique_citations:
            refs = resource_refs.get(key, {})
            ref_count = refs.get("ref_count", 1)
            ref_breakdown = refs.get("ref_breakdown", "")

            if key in verified:
                parts.append(
                    format_verification_result(
                        key,
                        verified[key],
                        ref_count,
                        ref_breakdown,
                        idx,
                    )
                )
            else:
                parts.append(f"  {idx}. {key}\n     Status: PENDING")
            idx += 1

    # Statutes
    statute_resources = [
        (r, cl)
        for r, cl in resolutions.items()
        if not isinstance(r.citation, FullCaseCitation)
    ]
    if statute_resources:
        parts.append("\nStatutes:")
        for i, (resource, cite_list) in enumerate(statute_resources, 1):
            primary = resource.citation
            count = len(cite_list)
            parts.append(
                f'  {i}. "{primary.matched_text()}" — {count} reference(s)'
            )

    # Unresolved
    if unresolved:
        parts.append("\nUnresolved:")
        for i, c in enumerate(unresolved, 1):
            label = citation_type_label(c)
            parts.append(f'  {i}. [{label}] "{c.matched_text()}"')

    return "\n".join(parts)


def format_resume(
    job_id: int,
    job: dict,
    newly_verified: set[str],
) -> str:
    """Format the resume output showing newly verified citations."""
    verified = job["verified"]
    pending = job["pending"]
    unique = job["unique_citations"]
    resource_refs = job["resource_refs"]
    total = len(unique)

    parts = [f"Citation Analysis (Job ID: {job_id}) — Resumed\n"]

    parts.append(f"Verification: {len(verified)} of {total} verified.")
    if pending:
        parts.append(
            f"({len(pending)} still pending — call "
            f"resume_citation_analysis again with job_id={job_id})"
        )
    else:
        parts.append("All citations verified!")

    if newly_verified:
        parts.append(f"\nNewly verified ({len(newly_verified)}):")
        idx = 1
        for key in unique:
            if key in newly_verified:
                refs = resource_refs.get(key, {})
                ref_count = refs.get("ref_count", 1)
                ref_breakdown = refs.get("ref_breakdown", "")
                parts.append(
                    format_verification_result(
                        key,
                        verified[key],
                        ref_count,
                        ref_breakdown,
                        idx,
                    )
                )
                idx += 1
    elif pending:
        parts.append(
            "\nNo new citations verified in this batch "
            "(may still be rate-limited)."
        )

    return "\n".join(parts)
