from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, model_validator

from courtlistener.utils import unflatten_filters


class Endpoint(BaseModel):
    """Base model for CourtListener API endpoints."""

    endpoint: ClassVar[str]
    endpoint_id: ClassVar[str]
    endpoint_name: ClassVar[str]

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def validate_filters(cls, data: Any) -> dict[str, Any]:
        assert isinstance(data, dict)
        return unflatten_filters(data)
