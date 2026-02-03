from datetime import datetime
from typing import Annotated, Any, ClassVar

from pydantic import BeforeValidator, Field

from courtlistener.models.endpoint import Endpoint
from courtlistener.models.filters import Filter6, Filter8
from courtlistener.utils import (
    related_validator,
)


class FinancialDisclosuresEndpoint(Endpoint):
    """Financial Disclosures Endpoint"""

    endpoint: ClassVar[str] = "/financial-disclosures/"
    endpoint_id: ClassVar[str] = "financial-disclosures"
    endpoint_name: ClassVar[str] = "Financial Disclosures"

    id: Annotated[
        None | int,
        Field(
            None,
        ),
    ]
    person: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "PeopleEndpoint",
            },
        ),
        BeforeValidator(related_validator),
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
    addendum_content_raw: Annotated[
        None | str | Filter6,
        Field(
            None,
            description="Raw content of addendum with whitespace preserved.",
        ),
    ]
    has_been_extracted: Annotated[
        None | bool,
        Field(
            None,
            description="Have we successfully extracted the data from PDF?",
        ),
    ]
    agreements: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "AgreementsEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]
    debts: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "DebtsEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]
    gifts: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "GiftsEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]
    investments: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "InvestmentsEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]
    non_investment_incomes: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "NonInvestmentIncomesEndpoint",
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
    reimbursements: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "ReimbursementsEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]
    spouse_incomes: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            json_schema_extra={
                "related_class_name": "SpouseIncomesEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]
