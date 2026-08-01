from fastmcp.exceptions import ToolError
from pydantic import ValidationError


class SentryExemptToolError(ToolError):
    """A `ToolError` triaged as known noise; not reported to Sentry."""


class ToolArgumentValidationError(ToolError):
    """Tool arguments failed input-schema validation."""

    def __init__(
        self, message: str, tool_name: str, argument_names: list[str]
    ) -> None:
        super().__init__(message)
        self.tool_name = tool_name
        self.argument_names = argument_names


class UnauthorizedToolError(ToolError):
    """CL rejected a freshly-verified token as unauthorized."""

    def __init__(self, message: str, tool_name: str) -> None:
        super().__init__(message)
        self.tool_name = tool_name


class SessionDataNotFoundError(ToolError):
    """A session-scoped ID (query, job) has no stored data."""

    def __init__(
        self, message: str, tool_name: str, argument_name: str
    ) -> None:
        super().__init__(message)
        self.tool_name = tool_name
        self.argument_name = argument_name


class UpstreamCourtListenerError(ToolError):
    """The upstream CL request failed: 5xx or transport error."""

    def __init__(self, message: str, tool_name: str, status: str) -> None:
        super().__init__(message)
        self.tool_name = tool_name
        self.status = status


def validation_error_fields(exc: ValidationError) -> list[str]:
    """Top-level field names that failed validation."""
    return sorted(
        {
            str(err["loc"][0]) if err["loc"] else "__root__"
            for err in exc.errors()
        }
    )


def before_send(event, hint):
    """Sentry `before_send` hook.

    - Drops exempt-marked tool errors.
    - ToolArgumentValidationErrors tagged by tool and arguments.
    - ValidationErrors tagged by model and fields.
    - UnauthorizedToolErrors tagged by tool.
    - UpstreamCourtListenerErrors keyed by status, tagged by tool and status.
    - SessionDataNotFoundErrors tagged by tool and field.
    """
    exc_info = hint.get("exc_info")
    exc = exc_info[1] if exc_info is not None else None
    if isinstance(exc, SentryExemptToolError):
        return None
    if isinstance(exc, SessionDataNotFoundError):
        event["fingerprint"] = ["session-data-not-found"]
        event.setdefault("tags", {}).update(
            {
                "tool": exc.tool_name,
                "field": exc.argument_name,
            }
        )
    elif isinstance(exc, UnauthorizedToolError):
        event["fingerprint"] = ["unauthorized-tool-call"]
        event.setdefault("tags", {}).update({"tool": exc.tool_name})
    elif isinstance(exc, UpstreamCourtListenerError):
        event["fingerprint"] = ["courtlistener-upstream", exc.status]
        event.setdefault("tags", {}).update(
            {
                "tool": exc.tool_name,
                "upstream_status": exc.status,
            }
        )
    elif isinstance(exc, ToolArgumentValidationError):
        event["fingerprint"] = ["tool-argument-validation"]
        event.setdefault("tags", {}).update(
            {
                "tool": exc.tool_name,
                "field": ",".join(exc.argument_names),
            }
        )
    elif isinstance(exc, ValidationError):
        event["fingerprint"] = ["endpoint-model-validation"]
        event.setdefault("tags", {}).update(
            {
                "model": exc.title,
                "field": ",".join(validation_error_fields(exc)),
            }
        )
    return event
