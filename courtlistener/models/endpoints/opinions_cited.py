from typing import Any, ClassVar, Annotated
from datetime import datetime, date

from pydantic import Field, ConfigDict, BeforeValidator, AfterValidator

from courtlistener.utils import (
    choice_validator,
    multiple_choice_validator,
    related_validator,
    in_pre_validator,
    try_coerce_ints,
    in_post_validator,
)
from courtlistener.models.endpoint import Endpoint


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


