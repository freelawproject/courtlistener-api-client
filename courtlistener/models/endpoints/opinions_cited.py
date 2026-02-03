from typing import Annotated, Any, ClassVar

from pydantic import BeforeValidator, Field

from courtlistener.models.endpoint import Endpoint
from courtlistener.utils import (
    related_validator,
)


class OpinionsCitedEndpoint(Endpoint):
    """Opinions Cited Endpoint"""

    endpoint: ClassVar[str] = "/opinions-cited/"
    endpoint_id: ClassVar[str] = "opinions-cited"
    endpoint_name: ClassVar[str] = "Opinions Cited"

    id: Annotated[
        None | int,
        Field(
            None,
        ),
    ]
    citing_opinion: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "OpinionsEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]
    cited_opinion: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "OpinionsEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]
