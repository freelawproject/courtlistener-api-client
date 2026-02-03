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


class DocketTagsEndpoint(Endpoint):
    """Docket Tags Endpoint"""

    endpoint: ClassVar[str] = "/docket-tags/"
    endpoint_id: ClassVar[str] = "docket-tags"
    endpoint_name: ClassVar[str] = "Docket Tags"

    id: Annotated[
        None | int,
        Field(
            None,
        ),
    ]
    docket: Annotated[
        None | int,
        Field(
            None,
        ),
    ]
    tag: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "TagsEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]


