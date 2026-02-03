from datetime import date, datetime
from typing import Annotated, Any, ClassVar

from pydantic import BeforeValidator, Field

from courtlistener.models.endpoint import Endpoint
from courtlistener.models.filters import Filter4, Filter7, Filter8
from courtlistener.utils import (
    choice_validator,
    multiple_choice_validator,
    related_validator,
)


class PeopleEndpoint(Endpoint):
    """People Endpoint"""

    endpoint: ClassVar[str] = "/people/"
    endpoint_id: ClassVar[str] = "people"
    endpoint_name: ClassVar[str] = "People"

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
    date_dob: Annotated[
        None | date | Filter7,
        Field(
            None,
            description="The date of birth for the person",
        ),
    ]
    date_dod: Annotated[
        None | date | Filter7,
        Field(
            None,
            description="The date of death for the person",
        ),
    ]
    name_first: Annotated[
        None | str | Filter4,
        Field(
            None,
            description="The first name of this person.",
        ),
    ]
    name_middle: Annotated[
        None | str | Filter4,
        Field(
            None,
            description="The middle name or names of this person",
        ),
    ]
    name_last: Annotated[
        None | str | Filter4,
        Field(
            None,
            description="The last name of this person",
        ),
    ]
    name_suffix: Annotated[
        None | str | Filter4,
        Field(
            None,
            description="Any suffixes that this person\u0027s name may have",
        ),
    ]
    is_alias_of: Annotated[
        None | int,
        Field(
            None,
        ),
    ]
    fjc_id: Annotated[
        None | int,
        Field(
            None,
            description="The ID of a judge as assigned by the Federal Judicial Center.",
        ),
    ]
    ftm_eid: Annotated[
        None | str,
        Field(
            None,
            description="The ID of a judge as assigned by the Follow the Money database.",
        ),
    ]
    dob_city: Annotated[
        None | str | Filter4,
        Field(
            None,
            description="The city where the person was born.",
        ),
    ]
    dob_state: Annotated[
        None | str | Filter4,
        Field(
            None,
            description="The state where the person was born.",
        ),
    ]
    dod_city: Annotated[
        None | str | Filter4,
        Field(
            None,
            description="The city where the person died.",
        ),
    ]
    dod_state: Annotated[
        None | str | Filter4,
        Field(
            None,
            description="The state where the person died.",
        ),
    ]
    gender: Annotated[
        None | str,
        Field(
            None,
            description="The person\u0027s gender",
            json_schema_extra={
                "choices": [
                    {"value": "m", "display_name": "Male"},
                    {"value": "f", "display_name": "Female"},
                    {"value": "o", "display_name": "Other"},
                ],
            },
        ),
        BeforeValidator(choice_validator),
    ]
    educations: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "EducationsEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]
    political_affiliations: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "PoliticalAffiliationsEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]
    sources: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "SourcesEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]
    aba_ratings: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "AbaRatingsEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]
    positions: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "PositionsEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]
    opinion_clusters_participating_judges: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "ClustersEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]
    opinion_clusters_non_participating_judges: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "ClustersEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]
    opinions_written: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "OpinionsEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]
    opinions_joined: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "OpinionsEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]
    race: Annotated[
        None | str | list[str],
        Field(
            None,
            json_schema_extra={
                "choices": [
                    {"value": "w", "display_name": "White"},
                    {
                        "value": "b",
                        "display_name": "Black or African American",
                    },
                    {
                        "value": "i",
                        "display_name": "American Indian or Alaska Native",
                    },
                    {"value": "a", "display_name": "Asian"},
                    {
                        "value": "p",
                        "display_name": "Native Hawaiian or Other Pacific Islander",
                    },
                    {
                        "value": "mena",
                        "display_name": "Middle Eastern/North African",
                    },
                    {"value": "h", "display_name": "Hispanic/Latino"},
                    {"value": "o", "display_name": "Other"},
                ],
            },
        ),
        BeforeValidator(multiple_choice_validator),
    ]
