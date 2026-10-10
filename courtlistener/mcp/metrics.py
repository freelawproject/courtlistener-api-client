import os
from collections.abc import Iterable, Mapping
from datetime import date

from fastmcp.server.dependencies import get_access_token
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    generate_latest,
    multiprocess,
)
from prometheus_client.core import GaugeMetricFamily, Metric
from prometheus_client.registry import Collector
from pydantic import ValidationError

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.auth_types import TokenKind
from courtlistener.mcp.exceptions import (
    SessionDataNotFoundError,
    ToolArgumentValidationError,
    UnauthorizedToolError,
    UpstreamCourtListenerError,
)
from courtlistener.mcp.session import (
    Session,
    get_session,
    token_user_key,
    utc_today,
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

oauth_registrations_total = Counter(
    "mcp_oauth_registrations_total",
    "OAuth clients registered with the MCP server, by source: dcr for a "
    "registration request, legacy for a CourtListener-issued client id "
    "recognised on first use",
    ["source"],
)

auth_rejections_total = Counter(
    "mcp_auth_rejections_total",
    "Requests whose credential the MCP server rejected, by scheme",
    ["scheme"],
)

OUTCOMES = (
    "ok",
    "validation_error",
    "session_data_not_found",
    "unauthorized",
    "rate_limited",
    "api_error",
    "upstream_error",
    "error",
)


def error_outcome(exc: BaseException) -> str:
    """Map a tool-call exception to a bounded outcome label."""
    if isinstance(exc, (ToolArgumentValidationError, ValidationError)):
        return "validation_error"
    if isinstance(exc, SessionDataNotFoundError):
        return "session_data_not_found"
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


ACTIVE_USER_WINDOWS = {"1d": 1, "7d": 7, "30d": 30}
"""Trailing windows of ``mcp_active_users``: label value to days."""

ActiveUserCounts = Mapping[tuple[str, str], int]
"""Distinct active users keyed by ``(window, credential)`` labels."""


class ActiveUsersCollector(Collector):
    """Exposes scrape-time active-user counts as ``mcp_active_users``."""

    def __init__(self, counts: ActiveUserCounts) -> None:
        self._counts = counts

    def collect(self) -> Iterable[Metric]:
        gauge = GaugeMetricFamily(
            "mcp_active_users",
            "Distinct MCP users active in the trailing window, by credential",
            labels=["window", "credential"],
        )
        for (window, credential), count in self._counts.items():
            gauge.add_metric([window, credential], count)
        yield gauge


async def active_user_counts(
    session: Session, today: date
) -> ActiveUserCounts | None:
    """Distinct active users per window and credential as of *today*.

    ``None`` when the store can't answer, so the scrape omits the gauge
    instead of reporting zeros.
    """
    counts: dict[tuple[str, str], int] = {}
    for window, days in ACTIVE_USER_WINDOWS.items():
        for kind in TokenKind:
            count = await session.active_users(kind.value, days, today)
            if count is None:
                return None
            counts[(window, kind.value)] = count
    return counts


class ActiveUserMarker:
    """Marks the request's user active once per UTC day per process."""

    def __init__(self) -> None:
        self._day: date | None = None
        self._marked: set[tuple[date, str, str]] = set()

    async def mark(self) -> None:
        """Mark the verified user active today; a no-op without a token."""
        access_token = get_access_token()
        if access_token is None:
            return
        credential = access_token.claims.get("token_kind", TokenKind.OAUTH)
        user_hash = token_user_key(access_token)
        today = utc_today()
        if today != self._day:
            self._day, self._marked = today, set()
        entry = (today, credential, user_hash)
        if entry in self._marked:
            return
        if await get_session().mark_active(user_hash, credential, today):
            self._marked.add(entry)


active_user_marker = ActiveUserMarker()


async def record_tool_call(tool: str, outcome: str) -> None:
    """Count a completed tool call and mark its user active."""
    tool_calls_total.labels(tool=tool, outcome=outcome).inc()
    await active_user_marker.mark()


async def render_metrics() -> tuple[bytes, str]:
    """Render the scrape payload and its content type.

    Under gunicorn, each worker owns a private registry, so a scrape would
    report one worker's counts. With PROMETHEUS_MULTIPROC_DIR set, the client
    library writes to per-process files instead, and this merges them.
    Active-user counts come from Redis at scrape time and are left out
    of the scrape when it is unreachable.
    """
    registry = CollectorRegistry()
    if "PROMETHEUS_MULTIPROC_DIR" in os.environ:
        multiprocess.MultiProcessCollector(registry)
    else:
        registry.register(REGISTRY)
    counts = await active_user_counts(get_session(), utc_today())
    if counts is not None:
        registry.register(ActiveUsersCollector(counts))
    return generate_latest(registry), CONTENT_TYPE_LATEST
