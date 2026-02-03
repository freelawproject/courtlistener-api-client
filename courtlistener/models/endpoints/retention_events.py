from datetime import date, datetime
from typing import Annotated, ClassVar

from pydantic import BeforeValidator, Field

from courtlistener.models.endpoint import Endpoint
from courtlistener.models.filters import Filter7, Filter8
from courtlistener.utils import (
    choice_validator,
)


class RetentionEventsEndpoint(Endpoint):
    """Retention Events Endpoint"""

    endpoint: ClassVar[str] = "/retention-events/"
    endpoint_id: ClassVar[str] = "retention-events"
    endpoint_name: ClassVar[str] = "Retention Events"

    id: Annotated[
        None | int,
        Field(
            None,
        ),
    ]
    position: Annotated[
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
    date_retention: Annotated[
        None | date | Filter7,
        Field(
            None,
            description="The date of retention",
        ),
    ]
    retention_type: Annotated[
        None | str,
        Field(
            None,
            description="The method through which this position was retained.",
            json_schema_extra={
                "choices": [
                    {
                        "value": "reapp_gov",
                        "display_name": "Governor Reappointment",
                    },
                    {
                        "value": "reapp_leg",
                        "display_name": "Legislative Reappointment",
                    },
                    {"value": "elec_p", "display_name": "Partisan Election"},
                    {
                        "value": "elec_n",
                        "display_name": "Nonpartisan Election",
                    },
                    {
                        "value": "elec_u",
                        "display_name": "Uncontested Election",
                    },
                ],
            },
        ),
        BeforeValidator(choice_validator),
    ]
    votes_yes: Annotated[
        None | int,
        Field(
            None,
            description="If votes are an integer, this is the number of votes in favor of a position.",
        ),
    ]
    votes_no: Annotated[
        None | int,
        Field(
            None,
            description="If votes are an integer, this is the number of votes opposed to a position.",
        ),
    ]
    unopposed: Annotated[
        None | bool,
        Field(
            None,
            description="Whether the position was unopposed at the time of retention.",
        ),
    ]
    won: Annotated[
        None | bool,
        Field(
            None,
            description="Whether the retention event was won.",
        ),
    ]
