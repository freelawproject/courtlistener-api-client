from __future__ import annotations

from typing import Any

from eyecite import get_citations, resolve_citations
from eyecite.models import FullCaseCitation
from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.exceptions import ToolArgumentValidationError
from courtlistener.mcp.session import get_session
from courtlistener.mcp.tools.citation_utils import (
    MAX_CITATIONS_PER_REQUEST,
    build_compact_string,
    canonical_key,
    citation_type_label,
    format_analysis,
    format_rate_limit_note,
    input_case_name,
    process_api_results,
)
from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.utils import (
    make_id,
    resolve_cluster_opinion_ids,
)


class AnalyzeCitationsTool(MCPTool):
    """Analyze and verify legal citations against CourtListener.

    Extracts all citations locally using eyecite, then verifies each
    unique case citation against CourtListener's database via the
    citation-lookup API. Returns case name, date, citation count,
    and verification status for each citation.

    For documents with more than 250 unique case citations, the first
    batch is verified immediately and a job_id is returned. Use
    resume_citation_analysis to continue verifying remaining citations.

    Terminology in the output:

    * **citation occurrence** — each citation as it appears in the text.
    * **unique citation string** — distinct ``volume reporter page``
      triples (e.g., one case cited three times is one string).
    * **unique case cluster** — distinct CourtListener case clusters
      after parallel-citation dedup (several strings may map to one).

    Case-name cross-check: when a citation verifies by reporter but
    its input case name differs significantly from the cluster's
    canonical name, a WARNING is emitted flagging a possible
    hallucinated citation.

    Input should include exactly one of opinion_id or cluster_id.
    """

    name: str = "analyze_citations"
    annotations = ToolAnnotations(
        title="Analyze Citations",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
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
                "cluster_id": {
                    "type": "integer",
                    "description": (
                        "ID of an opinion cluster (the `cluster_id` in "
                        "search results).  Analyzes the case's main "
                        "opinion; ids for any concurrences or dissents "
                        "are named in the output so they can be "
                        "analyzed separately."
                    ),
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    async def __call__(self, arguments: dict, ctx: Context) -> str:
        text = arguments.get("text")
        opinion_id = arguments.get("opinion_id")
        cluster_id = arguments.get("cluster_id")

        provided = [
            value
            for value in (text, opinion_id, cluster_id)
            if value is not None
        ]
        if len(provided) != 1:
            raise ToolArgumentValidationError(
                "Provide exactly one of text, opinion_id, or cluster_id.",
                tool_name=self.name,
                argument_names=["cluster_id", "opinion_id", "text"],
            )

        note = ""
        with self.get_client() as client:
            siblings = ""
            if cluster_id is not None:
                resolved = resolve_cluster_opinion_ids(cluster_id, client)
                opinion_id = resolved[0]
                if len(resolved) > 1:
                    siblings = (
                        "Analyze the others separately, one call per "
                        "opinion_id: "
                        f"{', '.join(str(i) for i in resolved[1:])}."
                    )
                    note = (
                        f"Analyzed opinion {opinion_id}, the main opinion "
                        f"of {len(resolved)} in cluster {cluster_id}. "
                        f"{siblings}\n\n"
                    )

            if opinion_id is not None:
                opinion = client.opinions.get(opinion_id)
                text = opinion.get("html_with_citations")
                if not text:
                    if cluster_id is not None:
                        raise ValueError(
                            f"Text not available for opinion {opinion_id} "
                            f"of cluster {cluster_id}. {siblings}".strip()
                        )
                    raise ValueError(
                        "Text not available for opinion ID. If this id "
                        "came from a search result it may be a "
                        "cluster_id, which is a separate id-space; pass "
                        "it as cluster_id instead."
                    )

            # Step 1: Local extraction and resolution
            assert text is not None  # for mypy
            cites = get_citations(text)
            if not cites:
                return note + "No citations found."

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

            # Step 2: Get unique case citation strings for API verification.
            # Also capture the input case name for each unique citation so we
            # can later warn when the verified cluster's name doesn't match.
            unique_citations: list[str] = []
            input_case_names: dict[str, str] = {}
            seen: set[str] = set()
            for resource in resolutions:
                primary = getattr(resource, "citation", None)
                if isinstance(primary, FullCaseCitation):
                    key = canonical_key(primary)
                    if key not in seen:
                        seen.add(key)
                        unique_citations.append(key)
                        name = input_case_name(primary)
                        if name:
                            input_case_names[key] = name

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

            rate_limit_detail: Any = None
            if sendable:
                batch = pending[:MAX_CITATIONS_PER_REQUEST]
                compact_text = build_compact_string(batch)
                try:
                    results = client.citation_lookup.lookup_text(compact_text)
                except CourtListenerAPIError as e:
                    if e.status_code != 429:
                        raise
                    rate_limit_detail = e.detail
                else:
                    process_api_results(results, batch, verified, pending)

            # Step 4: Store in user-scoped session store
            analysis_id = make_id()
            await get_session().store_citation_analysis(
                analysis_id,
                {
                    "resource_refs": resource_refs,
                    "unique_citations": unique_citations,
                    "input_case_names": input_case_names,
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
                input_case_names,
            )
            if rate_limit_detail is not None:
                output += "\n\n" + format_rate_limit_note(
                    rate_limit_detail,
                    resumable_with="resume_citation_analysis",
                )
            return note + output
