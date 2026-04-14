"""MCP tool to resume a rate-limited citation analysis."""

from __future__ import annotations

from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from courtlistener.mcp.tools.citation_utils import (
    MAX_CITATIONS_PER_REQUEST,
    build_compact_string,
    format_resume,
    process_api_results,
)
from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.utils import (
    get_session_citation_analysis,
    store_session_citation_analysis,
)


class ResumeCitationAnalysisTool(MCPTool):
    """Resume verifying citations from a previous analysis.

    Use this after analyze_citations returns with pending citations
    due to rate limiting (more than 250 unique case citations).
    Takes the job_id and verifies the next batch.
    """

    name: str = "resume_citation_analysis"
    annotations = ToolAnnotations(
        title="Resuming Citation Analysis",
        readOnlyHint=True,
        openWorldHint=True,
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": (
                        "The job ID (short UUID) from a previous "
                        "analyze_citations call."
                    ),
                },
            },
            "required": ["job_id"],
        }

    async def __call__(self, arguments: dict, ctx: Context) -> str:
        job_id = arguments["job_id"]
        job = await get_session_citation_analysis(job_id, ctx)

        if job is None:
            raise ValueError(
                f"Job ID {job_id!r} not found. The session may have expired."
            )

        pending = job["pending"]
        if not pending:
            return f"Job {job_id!r} is already complete.  All citations processed."

        # Verify next batch
        batch = pending[:MAX_CITATIONS_PER_REQUEST]
        compact_text = build_compact_string(batch)

        with self.get_client() as client:
            results = client.citation_lookup.lookup_text(compact_text)

        previously_verified = set(job["verified"].keys())
        process_api_results(results, batch, job["verified"], job["pending"])
        newly_verified = set(job["verified"].keys()) - previously_verified

        await store_session_citation_analysis(job_id, job, ctx)

        return format_resume(job_id, job, newly_verified)
