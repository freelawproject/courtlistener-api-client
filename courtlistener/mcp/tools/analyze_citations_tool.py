from __future__ import annotations

from eyecite import get_citations, resolve_citations
from eyecite.models import FullCaseCitation
from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from courtlistener.mcp.tools.citation_utils import (
    MAX_CITATIONS_PER_REQUEST,
    build_compact_string,
    canonical_key,
    citation_type_label,
    format_analysis,
    process_api_results,
)
from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.utils import (
    make_id,
    store_session_citation_analysis,
)


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
    annotations = ToolAnnotations(
        title="Analyzing Citations",
        readOnlyHint=True,
        openWorldHint=True,
    )

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

    async def __call__(self, arguments: dict, ctx: Context) -> str:
        text = arguments.get("text")
        opinion_id = arguments.get("opinion_id")
        if (text is not None) == (opinion_id is not None):
            raise ValueError(
                "Exactly one of text or opinion ID must be provided."
            )

        with self.get_client() as client:
            if opinion_id is not None:
                opinion = client.opinions.get(opinion_id)
                text = opinion.get("plain_text")
                if not text:
                    raise ValueError("Text not available for opinion ID.")

            # Step 1: Local extraction and resolution
            assert text is not None  # for mypy
            cites = get_citations(text)
            if not cites:
                return "No citations found."

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
                primary = getattr(resource, "citation", None)
                if isinstance(primary, FullCaseCitation):
                    key = canonical_key(primary)
                    if key not in seen:
                        seen.add(key)
                        unique_citations.append(key)

            # Step 3: Verify via API
            verified: dict[str, dict] = {}

            # Separate out citations with None page numbers (slip opinions).
            # These produce keys like "586 U. S. None" which the API cannot
            # resolve.  Mark them as unresolvable upfront rather than sending
            # them to the API where they'd silently get no result.
            sendable: list[str] = []
            for key in unique_citations:
                if key.endswith(" None"):
                    verified[key] = {
                        "status": None,
                        "citation": key,
                        "clusters": [],
                        "error_message": (
                            "Slip opinion citation without page number"
                        ),
                    }
                else:
                    sendable.append(key)

            pending = list(sendable)

            if sendable:
                batch = pending[:MAX_CITATIONS_PER_REQUEST]
                compact_text = build_compact_string(batch)
                results = client.citation_lookup.lookup_text(compact_text)
                process_api_results(results, batch, verified, pending)

            # Step 4: Store in user-scoped session store
            analysis_id = make_id()
            await store_session_citation_analysis(
                analysis_id,
                {
                    "resource_refs": resource_refs,
                    "unique_citations": unique_citations,
                    "verified": verified,
                    "pending": pending,
                },
                client,
            )

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
            return output
