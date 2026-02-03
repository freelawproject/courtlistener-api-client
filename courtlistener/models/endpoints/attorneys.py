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


class AttorneysEndpoint(Endpoint):
    """Attorneys Endpoint"""

    endpoint: ClassVar[str] = "/attorneys/"
    endpoint_id: ClassVar[str] = "attorneys"
    endpoint_name: ClassVar[str] = "Attorneys"

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
            description="The name of the attorney.",
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
    parties_represented: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "PartiesEndpoint",
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


