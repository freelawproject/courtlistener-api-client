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


class PrayersEndpoint(Endpoint):
    """Prayers Endpoint"""

    endpoint: ClassVar[str] = "/prayers/"
    endpoint_id: ClassVar[str] = "prayers"
    endpoint_name: ClassVar[str] = "Prayers"

    user: Annotated[
        None | int,
        Field(
            None,
        ),
    ]
    recap_document: Annotated[
        None | int,
        Field(
            None,
            description="The document you\u0027re praying for.",
        ),
    ]
    status: Annotated[
        None | int | list[int],
        Field(
            None,
            description="Whether the prayer has been granted or is still waiting.",
            json_schema_extra={
                "choices": [{'value': 1, 'display_name': 'Still waiting for the document.'}, {'value': 2, 'display_name': 'Prayer has been granted.'}],
            },
        ),
        AfterValidator(in_post_validator),
        BeforeValidator(multiple_choice_validator),
        BeforeValidator(try_coerce_ints),
        BeforeValidator(in_pre_validator),
    ]


