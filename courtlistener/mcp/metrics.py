import os

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    generate_latest,
    multiprocess,
)

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.exceptions import (
    SessionDataNotFoundError,
    ToolArgumentValidationError,
    UnauthorizedToolError,
    UpstreamCourtListenerError,
)

tool_calls_total = Counter(
    "mcp_tool_calls_total",
    "MCP tool calls by tool and outcome",
    ["tool", "outcome"],
)
"""
Usage:
    tool_calls_total.labels(tool="search", outcome="ok").inc()

Labels:
    tool: a registered tool name (see MCP_TOOLS)
    outcome: one of OUTCOMES
"""

OUTCOMES = (
    "ok",
    "validation_error",
    "unauthorized",
    "rate_limited",
    "api_error",
    "upstream_error",
    "error",
)


def outcome_for(exc: BaseException) -> str:
    """Map a tool-call exception to a bounded outcome label."""
    if isinstance(
        exc, (ToolArgumentValidationError, SessionDataNotFoundError)
    ):
        return "validation_error"
    if isinstance(exc, UnauthorizedToolError):
        return "unauthorized"
    if isinstance(exc, UpstreamCourtListenerError):
        return "upstream_error"
    cause = exc.__cause__
    if isinstance(cause, CourtListenerAPIError):
        if cause.status_code == 401:
            return "unauthorized"
        if cause.status_code == 429:
            return "rate_limited"
        if cause.status_code >= 500:
            return "upstream_error"
        return "api_error"
    return "error"


def render_metrics() -> tuple[bytes, str]:
    """Render the scrape payload and its content type.

    Under gunicorn, each worker owns a private registry, so a scrape would
    report one worker's counts. With PROMETHEUS_MULTIPROC_DIR set, the client
    library writes to per-process files instead, and this merges them.
    """
    if "PROMETHEUS_MULTIPROC_DIR" in os.environ:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    else:
        registry = REGISTRY
    return generate_latest(registry), CONTENT_TYPE_LATEST
