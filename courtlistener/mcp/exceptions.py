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
    """
    exc_info = hint.get("exc_info")
    exc = exc_info[1] if exc_info is not None else None
    if isinstance(exc, SentryExemptToolError):
        return None
    if isinstance(exc, ToolArgumentValidationError):
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
