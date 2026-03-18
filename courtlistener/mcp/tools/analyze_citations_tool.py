"""MCP tool for citation analysis with API verification."""

from __future__ import annotations

from eyecite import get_citations, resolve_citations
from eyecite.models import CitationBase, FullCaseCitation, Resource
from mcp.types import CallToolResult, TextContent

from courtlistener.mcp.tools.citation_utils import (
    build_compact_string,
    build_ref_breakdown,
    canonical_key,
    citation_type_label,
    extract_unique_case_citations,
    format_verification_result,
    next_analysis_id,
    summarize_cluster,
)
from courtlistener.mcp.tools.mcp_tool import MCPTool

# Maximum citations per API request before 429 throttling.
MAX_CITATIONS_PER_REQUEST = 250


class AnalyzeCitationsTool(MCPTool):
    """Analyze and verify legal citations against CourtListener.

    Extracts all citations locally using eyecite, then verifies each
    unique case citation against CourtListener's database via the
    citation-lookup API. Returns case name, date, citation count,
    and verification status for each citation.

    Uses a compact string strategy: only unique citation strings are
    sent to the API (not the full document text), minimizing payload
    size and API usage.

    For documents with more than 250 unique case citations, the first
    batch is verified immediately and a job_id is returned. Use
    resume_citation_analysis to continue verifying remaining citations.
    """

    name: str = "analyze_citations"

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": (
                        "Legal text to analyze. Citations will be "
                        "extracted locally and verified against "
                        "CourtListener."
                    ),
                },
            },
            "required": ["text"],
        }

    def __call__(self, arguments: dict, session: dict) -> CallToolResult:
        text = arguments["text"]

        # Step 1: Local extraction and resolution
        cites = get_citations(text)
        if not cites:
            return CallToolResult(
                content=[TextContent(type="text", text="No citations found.")]
            )

        resolutions = resolve_citations(cites)

        # Build per-resource reference info for output
        resource_refs = _build_resource_refs(resolutions)

        # Step 2: Get unique case citation strings for API verification
        unique_citations = extract_unique_case_citations(resolutions)

        # Step 3: Verify first batch via API
        verified: dict[str, dict] = {}
        pending = list(unique_citations)

        if unique_citations:
            batch = pending[:MAX_CITATIONS_PER_REQUEST]
            compact_text = build_compact_string(batch)

            with self.get_client() as client:
                results = client.citation_lookup.lookup_text(compact_text)

            _process_api_results(results, batch, verified, pending)

        # Step 4: Store in session
        analysis_id = next_analysis_id(session)
        session.setdefault("citation_analyses", {})[analysis_id] = {
            "resource_refs": resource_refs,
            "unique_citations": unique_citations,
            "verified": verified,
            "pending": pending,
        }

        # Step 5: Format output
        output = _format_analysis(
            analysis_id,
            cites,
            resolutions,
            resource_refs,
            unique_citations,
            verified,
            pending,
        )
        return CallToolResult(content=[TextContent(type="text", text=output)])


def _build_resource_refs(
    resolutions: dict[Resource, list[CitationBase]],
) -> dict[str, dict]:
    """Build a mapping of canonical citation key → reference info.

    Returns dict keyed by canonical citation string with:
    - ref_count: total number of references in the document
    - ref_breakdown: human-readable breakdown by type
    - cite_types: list of type labels
    """
    refs: dict[str, dict] = {}
    for resource, cite_list in resolutions.items():
        primary = resource.citation
        if isinstance(primary, FullCaseCitation):
            key = canonical_key(primary)
            count, breakdown = build_ref_breakdown(cite_list)
            refs[key] = {
                "ref_count": count,
                "ref_breakdown": breakdown,
            }
    return refs


def _process_api_results(
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
        matched_key = _match_to_batch(citation_text, batch)
        if matched_key is None:
            continue

        if status == 429:
            # Rate-limited — leave in pending
            continue

        # Summarize clusters to reduce stored data
        clusters = [summarize_cluster(c) for c in result.get("clusters", [])]

        verified[matched_key] = {
            "status": status,
            "citation": citation_text,
            "clusters": clusters,
            "error_message": result.get("error_message"),
        }
        if matched_key in pending:
            pending.remove(matched_key)


def _match_to_batch(citation_text: str, batch: list[str]) -> str | None:
    """Match an API result citation string to a batch entry.

    The API may return slightly different formatting, so we try
    exact match first, then normalized comparison.
    """
    # Exact match
    if citation_text in batch:
        return citation_text

    # Normalized match (strip whitespace, lowercase)
    normalized = citation_text.strip().lower()
    for key in batch:
        if key.strip().lower() == normalized:
            return key

    return None


def _format_analysis(
    analysis_id: int,
    cites: list[CitationBase],
    resolutions: dict[Resource, list[CitationBase]],
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
