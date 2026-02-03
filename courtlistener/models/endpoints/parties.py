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
from courtlistener.models.filters import Filter8
from courtlistener.models.filters import Filter6


class PartiesEndpoint(Endpoint):
    """Parties Endpoint"""

    endpoint: ClassVar[str] = "/parties/"
    endpoint_id: ClassVar[str] = "parties"
    endpoint_name: ClassVar[str] = "Parties"

    id: Annotated[
        None | int,
        Field(
            None,
        ),
    ]
    date_created: Annotated[
        None | datetime | Filter8,
        Field(
            None,
            description="The moment when the item was created.",
        ),
    ]
    date_modified: Annotated[
        None | datetime | Filter8,
        Field(
            None,
            description="The last moment when the item was modified. A value in year 1750 indicates the value is unknown",
        ),
    ]
    name: Annotated[
        None | str | Filter6,
        Field(
            None,
            description="The name of the party.",
        ),
    ]
    docket: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "DocketsEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]
    attorney: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "AttorneysEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]
    filter_nested_results: Annotated[
        None | bool,
        Field(
            None,
        ),
    ]


