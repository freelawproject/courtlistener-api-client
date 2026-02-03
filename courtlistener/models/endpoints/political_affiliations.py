from datetime import date, datetime
from typing import Annotated, ClassVar

from pydantic import BeforeValidator, Field

from courtlistener.models.endpoint import Endpoint
from courtlistener.models.filters import Filter7, Filter8
from courtlistener.utils import (
    choice_validator,
)


class PoliticalAffiliationsEndpoint(Endpoint):
    """Political Affiliations Endpoint"""

    endpoint: ClassVar[str] = "/political-affiliations/"
    endpoint_id: ClassVar[str] = "political-affiliations"
    endpoint_name: ClassVar[str] = "Political Affiliations"

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
    date_start: Annotated[
        None | date | Filter7,
        Field(
            None,
            description="The date the political affiliation was first documented",
        ),
    ]
    date_end: Annotated[
        None | date | Filter7,
        Field(
            None,
            description="The date the affiliation ended.",
        ),
    ]
    political_party: Annotated[
        None | str,
        Field(
            None,
            description="The political party the person is affiliated with.",
            json_schema_extra={
                "choices": [
                    {"value": "d", "display_name": "Democratic"},
                    {"value": "r", "display_name": "Republican"},
                    {"value": "i", "display_name": "Independent"},
                    {"value": "g", "display_name": "Green"},
                    {"value": "l", "display_name": "Libertarian"},
                    {"value": "f", "display_name": "Federalist"},
                    {"value": "w", "display_name": "Whig"},
                    {"value": "j", "display_name": "Jeffersonian Republican"},
                    {"value": "u", "display_name": "National Union"},
                    {"value": "z", "display_name": "Reform Party"},
                ],
            },
        ),
        BeforeValidator(choice_validator),
    ]
    source: Annotated[
        None | str,
        Field(
            None,
            description="The source of the political affiliation -- where it is documented that this affiliation exists.",
            json_schema_extra={
                "choices": [
                    {"value": "b", "display_name": "Ballot"},
                    {"value": "a", "display_name": "Appointer"},
                    {"value": "o", "display_name": "Other"},
                ],
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
