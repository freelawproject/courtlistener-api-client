from typing import Any

from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from courtlistener.mcp.tools.mcp_tool import MCPTool

SCOPE_DESCRIPTIONS = {
    "user": (
        "The main API quota. Governs nearly every endpoint and tool "
        "(search, call_endpoint, get_endpoint_item, read_document, alerts, "
        "...). This is the limit people mean by their API rate limit."
    ),
    "citations": (
        "Citation lookup quota, counted in citations rather than requests. "
        "Applies to analyze_citations and resume_citation_analysis only."
    ),
    "fetch": "PACER fetch requests (the recap-fetch endpoint) only.",
    "api_usage": (
        "Limits only this usage check itself. It says nothing about the "
        "user's real API limits; ignore it when answering questions about "
        "usage or rate limits."
    ),
}


class GetApiUsageTool(MCPTool):
    """Check the user's CourtListener API usage and rate limits.

    Returns live usage per throttle scope, daily request counts for the
    last 14 days, and membership status.

    The `user` scope is the one that matters: it is the main API quota
    and governs nearly every endpoint and tool. When the user asks about
    their rate limit, remaining requests, or 429 errors, answer from the
    `user` scope; `summary` states it in plain language. The other
    scopes are narrow: `citations` counts citation lookups, `fetch`
    counts PACER fetch requests, and `api_usage` only limits this usage
    check itself. Do not confuse `api_usage` with the user's API usage.

    Each limit reports `used`, `limit`, `remaining`, `reset_at` (null
    when the window is empty) and `blocked`. This tool never spends the
    `user` quota, so it works while other tools are rate limited.
    """

    name: str = "get_api_usage"
    annotations = ToolAnnotations(
        title="Get API Usage",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

    async def __call__(self, arguments: dict, ctx: Context) -> dict[str, Any]:
        async with self.get_client() as client:
            usage = await client.api_usage.get()

        by_scope: dict[str, list[dict[str, Any]]] = {}
        for row in usage.get("current_usage", []):
            by_scope.setdefault(row["scope"], []).append(row)

        ordered = [s for s in SCOPE_DESCRIPTIONS if s in by_scope] + [
            s for s in by_scope if s not in SCOPE_DESCRIPTIONS
        ]
        current_usage = {
            scope: {
                "description": SCOPE_DESCRIPTIONS.get(
                    scope, "Other throttle scope."
                ),
                "limits": by_scope[scope],
            }
            for scope in ordered
        }

        return {
            "summary": summarize_main_quota(by_scope.get("user", [])),
            "current_usage": current_usage,
            "historical_usage": usage.get("historical_usage"),
            "membership": usage.get("membership"),
        }


def summarize_main_quota(rows: list[dict[str, Any]]) -> str:
    """One sentence per `user` limit, in plain language."""
    if not rows:
        return "No main API quota (`user` scope) was reported."
    parts = []
    for row in rows:
        if row.get("blocked"):
            parts.append(
                f"API access is blocked (rate {row['rate']}); no requests "
                "are allowed."
            )
            continue
        reset = (
            f"the oldest request expires at {row['reset_at']}"
            if row.get("reset_at")
            else "the window is currently empty"
        )
        parts.append(
            f"{row['remaining']} of {row['limit']} API requests remaining "
            f"at {row['rate']} ({row['used']} used; {reset})."
        )
    return " ".join(parts)
