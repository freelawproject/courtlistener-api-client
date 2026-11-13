from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

# CourtListener stores a tag's name in a Django ``SlugField``.
TagName = Annotated[str, Field(pattern=r"^[-a-zA-Z0-9_]+$", max_length=50)]
TagDescription = Annotated[str, Field(max_length=250000)]


class TagsCreate(BaseModel):
    """Validation model for creating a tag."""

    model_config = ConfigDict(extra="forbid")

    name: TagName
    title: str | None = None
    description: TagDescription | None = None
    published: bool | None = None


class TagsUpdate(BaseModel):
    """Validation model for updating a tag."""

    model_config = ConfigDict(extra="forbid")

    name: TagName | None = None
    title: str | None = None
    description: TagDescription | None = None
    published: bool | None = None
