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


def validation_error_fingerprint(exc: ValidationError) -> list[str]:
    """Fingerprint suffix partitioning ValidationErrors by model + field."""
    fields = sorted(
        {
            str(err["loc"][0]) if err["loc"] else "__root__"
            for err in exc.errors()
        }
    )
    return ["{{ default }}", exc.title, *fields]


def before_send(event, hint):
    """Sentry `before_send` hook.

    - Drops exempt-marked tool errors.
    - Partitions tool-argument schema failures by tool + argument.
    - Partitions ValidationErrors by model + failing field(s).
    """
    exc_info = hint.get("exc_info")
    exc = exc_info[1] if exc_info is not None else None
    if isinstance(exc, SentryExemptToolError):
        return None
    if isinstance(exc, ToolArgumentValidationError):
        event["fingerprint"] = [
            "{{ default }}",
            exc.tool_name,
            *sorted(exc.argument_names),
        ]
    elif isinstance(exc, ValidationError):
        event["fingerprint"] = validation_error_fingerprint(exc)
    return event
