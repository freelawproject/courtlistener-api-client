from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DocketTagsCreate(BaseModel):
    """Validation model for adding a docket to a tag."""

    model_config = ConfigDict(extra="forbid")

    tag: int
    docket: int
