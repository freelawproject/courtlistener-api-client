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
from courtlistener.models.filters import Filter6
from courtlistener.models.filters import Filter6


class GiftsEndpoint(Endpoint):
    """Gifts Endpoint"""

    endpoint: ClassVar[str] = "/gifts/"
    endpoint_id: ClassVar[str] = "gifts"
    endpoint_name: ClassVar[str] = "Gifts"

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
    source: Annotated[
        None | str | Filter6,
        Field(
            None,
            description="Source of the judicial gift. (ex. Alta Ski Area).",
        ),
    ]
    description: Annotated[
        None | str | Filter6,
        Field(
            None,
            description="Description of the gift (ex. Season Pass).",
        ),
    ]
    value: Annotated[
        None | str | Filter6,
        Field(
            None,
            description="Value of the judicial gift, (ex. $1,199.00)",
        ),
    ]
    redacted: Annotated[
        None | bool,
        Field(
            None,
            description="Does the gift row contain redaction(s)?",
        ),
    ]
    financial_disclosure: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            description="The financial disclosure associated with this gift.",
            json_schema_extra={
                "related_class_name": "FinancialDisclosuresEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]


