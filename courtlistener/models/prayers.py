from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PrayerCreate(BaseModel):
    """Validation model for creating a prayer."""

    model_config = ConfigDict(extra="forbid")

    recap_document: int
