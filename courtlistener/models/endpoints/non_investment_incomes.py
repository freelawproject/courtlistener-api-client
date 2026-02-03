from datetime import datetime
from typing import Annotated, Any, ClassVar

from pydantic import BeforeValidator, Field

from courtlistener.models.endpoint import Endpoint
from courtlistener.models.filters import Filter6, Filter8
from courtlistener.utils import (
    related_validator,
)


class NonInvestmentIncomesEndpoint(Endpoint):
    """Non Investment Incomes Endpoint"""

    endpoint: ClassVar[str] = "/non-investment-incomes/"
    endpoint_id: ClassVar[str] = "non-investment-incomes"
    endpoint_name: ClassVar[str] = "Non Investment Incomes"

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
            description="Does the non-investment income row contain redaction(s)?",
        ),
    ]
    date_raw: Annotated[
        None | str | Filter6,
        Field(
            None,
            description="Date of non-investment income (ex. 2011).",
        ),
    ]
    source_type: Annotated[
        None | str | Filter6,
        Field(
            None,
            description="Source and type of non-investment income for the judge (ex. Teaching a class at U. Miami).",
        ),
    ]
    income_amount: Annotated[
        None | str | Filter6,
        Field(
            None,
            description="Amount earned by judge, often a number, but sometimes with explanatory text (e.g. \u0027Income at firm: $xyz\u0027).",
        ),
    ]
    financial_disclosure: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            description="The financial disclosure associated with this non-investment income.",
            json_schema_extra={
                "related_class_name": "FinancialDisclosuresEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]
