from fastmcp.exceptions import ToolError
from pydantic import ValidationError


class SentryExemptToolError(ToolError):
    """A `ToolError` triaged as known noise; not reported to Sentry."""


class ToolArgumentValidationError(ToolError):
    """Tool arguments failed input-schema validation."""

    def __init__(self, message: str, tool_name: str) -> None:
        super().__init__(message)
        self.tool_name = tool_name


def before_send(event, hint):
    """Sentry `before_send` hook.

    - Drops exempt-marked tool errors.
    - Partitions tool-argument schema failures by tool.
    - Partitions ValidationErrors by model.
    """
    exc_info = hint.get("exc_info")
    exc = exc_info[1] if exc_info is not None else None
    if isinstance(exc, SentryExemptToolError):
        return None
    if isinstance(exc, ToolArgumentValidationError):
        event["fingerprint"] = ["{{ default }}", exc.tool_name]
    elif isinstance(exc, ValidationError):
        event["fingerprint"] = ["{{ default }}", exc.title]
    return event
