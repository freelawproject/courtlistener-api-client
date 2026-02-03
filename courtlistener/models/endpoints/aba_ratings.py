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


class AbaRatingsEndpoint(Endpoint):
    """Aba Ratings Endpoint"""

    endpoint: ClassVar[str] = "/aba-ratings/"
    endpoint_id: ClassVar[str] = "aba-ratings"
    endpoint_name: ClassVar[str] = "Aba Ratings"

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
    year_rated: Annotated[
        None | int,
        Field(
            None,
            description="The year of the rating.",
        ),
    ]
    rating: Annotated[
        None | str,
        Field(
            None,
            description="The rating given to the person.",
            json_schema_extra={
                "choices": [{'value': 'ewq', 'display_name': 'Exceptionally Well Qualified'}, {'value': 'wq', 'display_name': 'Well Qualified'}, {'value': 'q', 'display_name': 'Qualified'}, {'value': 'nq', 'display_name': 'Not Qualified'}, {'value': 'nqa', 'display_name': 'Not Qualified By Reason of Age'}],
            },
        ),
        BeforeValidator(choice_validator),
    ]
    person: Annotated[
        None | int,
        Field(
            None,
        ),
    ]


