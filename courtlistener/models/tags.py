from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

# CourtListener stores a tag's name in a Django ``SlugField``.
TAG_NAME_PATTERN = r"^[-a-zA-Z0-9_]+$"
TAG_NAME_MAX_LENGTH = 50

TagName = Annotated[
    str, Field(pattern=TAG_NAME_PATTERN, max_length=TAG_NAME_MAX_LENGTH)
]


class TagCreate(BaseModel):
    """Validation model for creating a tag."""

    model_config = ConfigDict(extra="forbid")

    name: TagName
    title: str | None = None
    description: str | None = None
    published: bool | None = None


class TagUpdate(BaseModel):
    """Validation model for updating a tag."""

    model_config = ConfigDict(extra="forbid")

    name: TagName | None = None
    title: str | None = None
    description: str | None = None
    published: bool | None = None


class DocketTagCreate(BaseModel):
    """Validation model for adding a docket to a tag."""

    model_config = ConfigDict(extra="forbid")

    tag: int
    docket: int
