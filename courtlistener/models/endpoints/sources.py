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
from courtlistener.models.filters import Filter8


class SourcesEndpoint(Endpoint):
    """Sources Endpoint"""

    endpoint: ClassVar[str] = "/sources/"
    endpoint_id: ClassVar[str] = "sources"
    endpoint_name: ClassVar[str] = "Sources"

    id: Annotated[
        None | int,
        Field(
            None,
        ),
    ]
    date_modified: Annotated[
        None | datetime | Filter8,
        Field(
            None,
            description="The last moment when the item was modified. A value in year 1750 indicates the value is unknown",
        ),
    ]
    person: Annotated[
        None | int,
        Field(
            None,
        ),
    ]


