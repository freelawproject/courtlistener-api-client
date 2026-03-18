"""MCP tool to resume a rate-limited citation analysis."""

from __future__ import annotations

from mcp.types import CallToolResult, TextContent

from courtlistener.mcp.tools.analyze_citations_tool import (
    MAX_CITATIONS_PER_REQUEST,
    _process_api_results,
)
from courtlistener.mcp.tools.citation_utils import (
    build_compact_string,
    format_verification_result,
)
from courtlistener.mcp.tools.mcp_tool import MCPTool


class ResumeCitationAnalysisTool(MCPTool):
    """Resume verifying citations from a previous analysis.

    Use this after analyze_citations returns with pending citations
    due to rate limiting (more than 250 unique case citations).
    Takes the job_id and verifies the next batch.
    """

    name: str = "resume_citation_analysis"

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "integer",
                    "description": (
                        "The job ID from a previous analyze_citations call."
                    ),
                },
            },
            "required": ["job_id"],
        }

    def __call__(self, arguments: dict, session: dict) -> CallToolResult:
        job_id = arguments["job_id"]
        analyses = session.get("citation_analyses", {})
        job = analyses.get(job_id)

        if job is None:
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=(
                            f"Job ID {job_id} not found. "
                            "The session may have expired."
                        ),
                    )
                ],
                isError=True,
            )

        pending = job["pending"]
        if not pending:
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=(
                            f"Job {job_id} is already complete. "
                            "All citations verified."
                        ),
                    )
                ]
            )

        # Verify next batch
        batch = pending[:MAX_CITATIONS_PER_REQUEST]
        compact_text = build_compact_string(batch)

        with self.get_client() as client:
            results = client.citation_lookup.lookup_text(compact_text)

        previously_verified = set(job["verified"].keys())
        _process_api_results(results, batch, job["verified"], job["pending"])
        newly_verified = set(job["verified"].keys()) - previously_verified

        # Format output
        output = _format_resume(job_id, job, newly_verified)
        return CallToolResult(content=[TextContent(type="text", text=output)])


def _format_resume(
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
