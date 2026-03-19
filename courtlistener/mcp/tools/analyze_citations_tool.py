from __future__ import annotations

from eyecite import get_citations, resolve_citations
from eyecite.models import FullCaseCitation
from mcp.types import CallToolResult, TextContent

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.tools.citation_utils import (
    MAX_CITATIONS_PER_REQUEST,
    build_compact_string,
    canonical_key,
    citation_type_label,
    format_analysis,
    process_api_results,
)
from courtlistener.mcp.tools.mcp_tool import MCPTool


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
                "opinion_id": {
                    "type": "integer",
                    "description": (
                        "Alternatively, if the opinion is available "
                        "in CourtListener, you can provide the opinion ID"
                    ),
                },
            },
            "required": [],
        }

    def __call__(self, arguments: dict, session: dict) -> CallToolResult:
        text = arguments.get("text")
        opinion_id = arguments.get("opinion_id")
        if (text is not None) == (opinion_id is not None):
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text="Exactly one of text or opinion ID must be provided.",
                    )
                ],
                isError=True,
            )

        if opinion_id is not None:
            with self.get_client(session) as client:
                try:
                    opinion = client.opinions.get(opinion_id)
                except CourtListenerAPIError as exc:
                    return CallToolResult(
                        content=[TextContent(type="text", text=str(exc))],
                        isError=True,
                    )
                text = opinion.get("plain_text")
                if not text:
                    return CallToolResult(
                        content=[
                            TextContent(
                                type="text",
                                text="Text not available for opinion ID.",
                            )
                        ],
                        isError=True,
                    )

        # Step 1: Local extraction and resolution
        assert text is not None  # for mypy
        cites = get_citations(text)
        if not cites:
            return CallToolResult(
                content=[TextContent(type="text", text="No citations found.")]
            )

        resolutions = resolve_citations(cites)

        # Build per-resource reference info for output
        resource_refs: dict[str, dict] = {}
        for resource, cite_list in resolutions.items():
            if hasattr(resource, "citation"):
                primary = resource.citation
                if isinstance(primary, FullCaseCitation):
                    key = canonical_key(primary)
                    counts: dict[str, int] = {}
                    for c in cite_list:
                        label = citation_type_label(c)
                        counts[label] = counts.get(label, 0) + 1
                    total = sum(counts.values())
                    parts = [f"{v} {k}" for k, v in counts.items()]
                    breakdown = ", ".join(parts)
                    resource_refs[key] = {
                        "ref_count": total,
                        "ref_breakdown": breakdown,
                    }

        # Step 2: Get unique case citation strings for API verification
        unique_citations: list[str] = []
        seen: set[str] = set()
        for resource in resolutions:
            primary = resource.citation
            if isinstance(primary, FullCaseCitation):
                key = canonical_key(primary)
                if key not in seen:
                    seen.add(key)
                    unique_citations.append(key)

        # Step 3: Verify first batch via API
        verified: dict[str, dict] = {}
        pending = list(unique_citations)

        if unique_citations:
            batch = pending[:MAX_CITATIONS_PER_REQUEST]
            compact_text = build_compact_string(batch)

            with self.get_client(session) as client:
                results = client.citation_lookup.lookup_text(compact_text)

            process_api_results(results, batch, verified, pending)

        # Step 4: Store in session
        analyses = session.get("citation_analyses", {})
        analysis_id = 1 if not analyses else max(analyses.keys()) + 1
        session.setdefault("citation_analyses", {})[analysis_id] = {
            "resource_refs": resource_refs,
            "unique_citations": unique_citations,
            "verified": verified,
            "pending": pending,
        }

        # Step 5: Format output
        output = format_analysis(
            analysis_id,
            cites,
            resolutions,
            resource_refs,
            unique_citations,
            verified,
            pending,
        )
        return CallToolResult(content=[TextContent(type="text", text=output)])
