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
from courtlistener.models.filters import Filter4


class TagsEndpoint(Endpoint):
    """Tags Endpoint"""

    endpoint: ClassVar[str] = "/tags/"
    endpoint_id: ClassVar[str] = "tags"
    endpoint_name: ClassVar[str] = "Tags"

    id: Annotated[
        None | int,
        Field(
            None,
        ),
    ]
    user: Annotated[
        None | int,
        Field(
            None,
        ),
    ]
    name: Annotated[
        None | str | Filter4,
        Field(
            None,
            description="The name of the tag",
        ),
    ]
    published: Annotated[
        None | bool,
        Field(
            None,
            description="Whether the tag has been shared publicly.",
        ),
    ]


