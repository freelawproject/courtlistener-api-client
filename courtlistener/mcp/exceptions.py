from fastmcp.exceptions import ToolError
from pydantic import ValidationError


class SentryExemptToolError(ToolError):
    """A `ToolError` triaged as known noise; not reported to Sentry."""


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
    - Partitions ValidationErrors by model + failing field(s).
    """
    exc_info = hint.get("exc_info")
    exc = exc_info[1] if exc_info is not None else None
    if isinstance(exc, SentryExemptToolError):
        return None
    if isinstance(exc, ValidationError):
        event["fingerprint"] = validation_error_fingerprint(exc)
    return event
