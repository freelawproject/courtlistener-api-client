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


class InvestmentsEndpoint(Endpoint):
    """Investments Endpoint"""

    endpoint: ClassVar[str] = "/investments/"
    endpoint_id: ClassVar[str] = "investments"
    endpoint_name: ClassVar[str] = "Investments"

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
    redacted: Annotated[
        None | bool,
        Field(
            None,
            description="Does the investment row contains redaction(s)?",
        ),
    ]
    description: Annotated[
        None | str | Filter6,
        Field(
            None,
            description="Name of investment (ex. APPL common stock).",
        ),
    ]
    gross_value_code: Annotated[
        None | str,
        Field(
            None,
            description="Investment total value code at end of reporting period as code (ex. J (1-15,000)).",
            json_schema_extra={
                "choices": [{'value': 'J', 'display_name': '1 - 15,000'}, {'value': 'K', 'display_name': '15,001 - 50,000'}, {'value': 'L', 'display_name': '50,001 - 100,000'}, {'value': 'M', 'display_name': '100,001 - 250,000'}, {'value': 'N', 'display_name': '250,001 - 500,000'}, {'value': 'O', 'display_name': '500,001 - 1,000,000'}, {'value': 'P1', 'display_name': '1,000,001 - 5,000,000'}, {'value': 'P2', 'display_name': '5,000,001 - 25,000,000'}, {'value': 'P3', 'display_name': '25,000,001 - 50,000,000'}, {'value': 'P4', 'display_name': '50,000,001 - '}, {'value': '-1', 'display_name': 'Failed Extraction'}],
            },
        ),
        BeforeValidator(choice_validator),
    ]
    income_during_reporting_period_code: Annotated[
        None | str,
        Field(
            None,
            description="Increase in investment value - as a form code",
            json_schema_extra={
                "choices": [{'value': 'A', 'display_name': '1 - 1,000'}, {'value': 'B', 'display_name': '1,001 - 2,500'}, {'value': 'C', 'display_name': '2,501 - 5,000'}, {'value': 'D', 'display_name': '5,001 - 15,000'}, {'value': 'E', 'display_name': '15,001 - 50,000'}, {'value': 'F', 'display_name': '50,001 - 100,000'}, {'value': 'G', 'display_name': '100,001 - 1,000,000'}, {'value': 'H1', 'display_name': '1,000,001 - 5,000,000'}, {'value': 'H2', 'display_name': '5,000,001 +'}, {'value': '-1', 'display_name': 'Failed Extraction'}],
            },
        ),
        BeforeValidator(choice_validator),
    ]
    transaction_during_reporting_period: Annotated[
        None | str | Filter6,
        Field(
            None,
            description="Transaction of investment during reporting period (ex. Buy, Sold)",
        ),
    ]
    transaction_value_code: Annotated[
        None | str,
        Field(
            None,
            description="Transaction value amount, as form code (ex. J (1-15,000)).",
            json_schema_extra={
                "choices": [{'value': 'J', 'display_name': '1 - 15,000'}, {'value': 'K', 'display_name': '15,001 - 50,000'}, {'value': 'L', 'display_name': '50,001 - 100,000'}, {'value': 'M', 'display_name': '100,001 - 250,000'}, {'value': 'N', 'display_name': '250,001 - 500,000'}, {'value': 'O', 'display_name': '500,001 - 1,000,000'}, {'value': 'P1', 'display_name': '1,000,001 - 5,000,000'}, {'value': 'P2', 'display_name': '5,000,001 - 25,000,000'}, {'value': 'P3', 'display_name': '25,000,001 - 50,000,000'}, {'value': 'P4', 'display_name': '50,000,001 - '}, {'value': '-1', 'display_name': 'Failed Extraction'}],
            },
        ),
        BeforeValidator(choice_validator),
    ]
    financial_disclosure: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            description="The financial disclosure associated with this investment.",
            json_schema_extra={
                "related_class_name": "FinancialDisclosuresEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]


