from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PrayersCreate(BaseModel):
    """Validation model for creating a prayer."""

    model_config = ConfigDict(extra="forbid")

    recap_document: int
