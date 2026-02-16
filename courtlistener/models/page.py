from typing import Any

from pydantic import BaseModel, ConfigDict


class Page(BaseModel):
    """A paginated response from the CourtListener API."""

    count: str | int | None = None
    document_count: int | None = None
    next: str | None = None
    previous: str | None = None
    results: list[dict[str, Any]]

    model_config = ConfigDict(extra="forbid")
