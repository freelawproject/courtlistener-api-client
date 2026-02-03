from datetime import datetime
from typing import Annotated, Any, ClassVar

from pydantic import BeforeValidator, Field

from courtlistener.models.endpoint import Endpoint
from courtlistener.models.filters import Filter6, Filter8
from courtlistener.utils import (
    choice_validator,
    related_validator,
)


class DebtsEndpoint(Endpoint):
    """Debts Endpoint"""

    endpoint: ClassVar[str] = "/debts/"
    endpoint_id: ClassVar[str] = "debts"
    endpoint_name: ClassVar[str] = "Debts"

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
            description="Does the debt row contain redaction(s)?",
        ),
    ]
    creditor_name: Annotated[
        None | str | Filter6,
        Field(
            None,
            description="Liability/Debt creditor",
        ),
    ]
    description: Annotated[
        None | str | Filter6,
        Field(
            None,
            description="Description of the debt",
        ),
    ]
    value_code: Annotated[
        None | str,
        Field(
            None,
            description="Form code for the value of the judicial debt.",
            json_schema_extra={
                "choices": [
                    {"value": "J", "display_name": "1 - 15,000"},
                    {"value": "K", "display_name": "15,001 - 50,000"},
                    {"value": "L", "display_name": "50,001 - 100,000"},
                    {"value": "M", "display_name": "100,001 - 250,000"},
                    {"value": "N", "display_name": "250,001 - 500,000"},
                    {"value": "O", "display_name": "500,001 - 1,000,000"},
                    {"value": "P1", "display_name": "1,000,001 - 5,000,000"},
                    {"value": "P2", "display_name": "5,000,001 - 25,000,000"},
                    {"value": "P3", "display_name": "25,000,001 - 50,000,000"},
                    {"value": "P4", "display_name": "50,000,001 - "},
                    {"value": "-1", "display_name": "Failed Extraction"},
                ],
            },
        ),
        BeforeValidator(choice_validator),
    ]
    financial_disclosure: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            description="The financial disclosure associated with this debt.",
            json_schema_extra={
                "related_class_name": "FinancialDisclosuresEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]
