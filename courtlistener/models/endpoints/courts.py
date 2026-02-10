from datetime import date, datetime
from typing import Annotated, Any, ClassVar

from pydantic import BeforeValidator, Field

from courtlistener.models.endpoint import Endpoint
from courtlistener.models.filters import Filter6, Filter7, Filter8
from courtlistener.utils import (
    multiple_choice_validator,
    related_validator,
)


class CourtsEndpoint(Endpoint):
    """Courts Endpoint"""

    endpoint: ClassVar[str] = "/courts/"
    endpoint_id: ClassVar[str] = "courts"
    endpoint_name: ClassVar[str] = "Courts"

    id: Annotated[
        None | str,
        Field(
            None,
        ),
    ]
    date_modified: Annotated[
        None | datetime | Filter8,
        Field(
            None,
            description="The last moment when the item was modified",
        ),
    ]
    in_use: Annotated[
        None | bool,
        Field(
            None,
            description="Whether this jurisdiction is in use in CourtListener -- increasingly True",
        ),
    ]
    has_opinion_scraper: Annotated[
        None | bool,
        Field(
            None,
            description="Whether the jurisdiction has a scraper that obtains opinions automatically.",
        ),
    ]
    has_oral_argument_scraper: Annotated[
        None | bool,
        Field(
            None,
            description="Whether the jurisdiction has a scraper that obtains oral arguments automatically.",
        ),
    ]
    position: Annotated[
        None | int,
        Field(
            None,
            description="A dewey-decimal-style numeral indicating a hierarchical ordering of jurisdictions",
        ),
    ]
    start_date: Annotated[
        None | date | Filter7,
        Field(
            None,
            description="the date the court was established, if known",
        ),
    ]
    end_date: Annotated[
        None | date | Filter7,
        Field(
            None,
            description="the date the court was abolished, if known",
        ),
    ]
    short_name: Annotated[
        None | str | Filter6,
        Field(
            None,
            description="a short name of the court",
        ),
    ]
    full_name: Annotated[
        None | str | Filter6,
        Field(
            None,
            description="the full name of the court",
        ),
    ]
    citation_string: Annotated[
        None | str | Filter6,
        Field(
            None,
            description="the citation abbreviation for the court as dictated by Blue Book",
        ),
    ]
    dockets: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "DocketsEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]
    jurisdiction: Annotated[
        None | str | list[str],
        Field(
            None,
            description="the jurisdiction of the court, one of: F (Federal Appellate), FD (Federal District), FB (Federal Bankruptcy), FBP (Federal Bankruptcy Panel), FS (Federal Special), S (State Supreme), SA (State Appellate), ST (State Trial), SS (State Special), TRS (Tribal Supreme), TRA (Tribal Appellate), TRT (Tribal Trial), TRX (Tribal Special), TS (Territory Supreme), TA (Territory Appellate), TT (Territory Trial), TSP (Territory Special), SAG (State Attorney General), MA (Military Appellate), MT (Military Trial), C (Committee), I (International), T (Testing)",
            json_schema_extra={
                "choices": [
                    {"value": "F", "display_name": "Federal Appellate"},
                    {"value": "FD", "display_name": "Federal District"},
                    {"value": "FB", "display_name": "Federal Bankruptcy"},
                    {
                        "value": "FBP",
                        "display_name": "Federal Bankruptcy Panel",
                    },
                    {"value": "FS", "display_name": "Federal Special"},
                    {"value": "S", "display_name": "State Supreme"},
                    {"value": "SA", "display_name": "State Appellate"},
                    {"value": "ST", "display_name": "State Trial"},
                    {"value": "SS", "display_name": "State Special"},
                    {"value": "TRS", "display_name": "Tribal Supreme"},
                    {"value": "TRA", "display_name": "Tribal Appellate"},
                    {"value": "TRT", "display_name": "Tribal Trial"},
                    {"value": "TRX", "display_name": "Tribal Special"},
                    {"value": "TS", "display_name": "Territory Supreme"},
                    {"value": "TA", "display_name": "Territory Appellate"},
                    {"value": "TT", "display_name": "Territory Trial"},
                    {"value": "TSP", "display_name": "Territory Special"},
                    {"value": "SAG", "display_name": "State Attorney General"},
                    {"value": "MA", "display_name": "Military Appellate"},
                    {"value": "MT", "display_name": "Military Trial"},
                    {"value": "C", "display_name": "Committee"},
                    {"value": "I", "display_name": "International"},
                    {"value": "T", "display_name": "Testing"},
                ],
            },
        ),
        BeforeValidator(multiple_choice_validator),
    ]
    parent_court: Annotated[
        None | str,
        Field(
            None,
            description="Parent court for subdivisions",
        ),
    ]
