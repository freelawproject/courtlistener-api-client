"""MCP tool to resume a rate-limited citation analysis."""

from __future__ import annotations

from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.exceptions import SessionDataNotFoundError
from courtlistener.mcp.session import get_session
from courtlistener.mcp.tools.citation_utils import (
    MAX_CITATIONS_PER_REQUEST,
    build_compact_string,
    format_rate_limit_note,
    format_resume,
    process_api_results,
)
from courtlistener.mcp.tools.mcp_tool import MCPTool


class ResumeCitationAnalysisTool(MCPTool):
    """Resume verifying citations from a previous analysis.

    Use this after analyze_citations returns with pending citations
    due to rate limiting (more than 250 unique case citations).
    Takes the job_id and verifies the next batch.
    """

    name: str = "resume_citation_analysis"
    annotations = ToolAnnotations(
        title="Resume Citation Analysis",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=False,
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
                "wait": {
                    "type": "boolean",
                    "description": (
                        "If true, the server sleeps through the upstream "
                        "rate-limit window (capped at ~90s) and retries "
                        "automatically. Use this after a previous call "
                        "reported a short wait_until. Default false: the "
                        "tool returns immediately on rate limit so you can "
                        "tell the user before waiting."
                    ),
                    "default": False,
                },
            },
            "required": ["job_id"],
            "additionalProperties": False,
        }

    async def __call__(self, arguments: dict, ctx: Context) -> str:
        job_id = arguments["job_id"]
        wait = bool(arguments.get("wait", False))
        with self.get_client() as client:
            job = await get_session().get_citation_analysis(job_id, client)
            if job is None:
                raise SessionDataNotFoundError(
                    f"Job ID {job_id!r} not found. The session may have "
                    "expired.",
                    tool_name=self.name,
                    argument_name="job_id",
                )

            pending = job["pending"]
            if not pending:
                return f"Job {job_id!r} is already complete.  All citations processed."

            # Verify next batch
            batch = pending[:MAX_CITATIONS_PER_REQUEST]
            compact_text = build_compact_string(batch)
            try:
                results = client.citation_lookup.lookup_text(
                    compact_text, retry_on_rate_limit=wait
                )
            except CourtListenerAPIError as e:
                if e.status_code != 429:
                    raise
                return (
                    format_resume(job_id, job, set())
                    + "\n\n"
                    + format_rate_limit_note(
                        e.detail,
                        resumable_with="resume_citation_analysis",
                    )
                )

            previously_verified = set(job["verified"].keys())
            process_api_results(
                results, batch, job["verified"], job["pending"]
            )
            newly_verified = set(job["verified"].keys()) - previously_verified

            await get_session().store_citation_analysis(job_id, job, client)

            return format_resume(job_id, job, newly_verified)
