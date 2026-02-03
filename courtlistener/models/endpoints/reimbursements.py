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
from courtlistener.models.filters import Filter6
from courtlistener.models.filters import Filter6
from courtlistener.models.filters import Filter6


class ReimbursementsEndpoint(Endpoint):
    """Reimbursements Endpoint"""

    endpoint: ClassVar[str] = "/reimbursements/"
    endpoint_id: ClassVar[str] = "reimbursements"
    endpoint_name: ClassVar[str] = "Reimbursements"

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
            description="Does the reimbursement contain redaction(s)?",
        ),
    ]
    date_raw: Annotated[
        None | str | Filter6,
        Field(
            None,
            description="Dates as a text string for the date of reimbursements. This is often conference dates (ex. June 2-6, 2011).",
        ),
    ]
    location: Annotated[
        None | str | Filter6,
        Field(
            None,
            description="Location of the reimbursement (ex. Harvard Law School, Cambridge, MA).",
        ),
    ]
    source: Annotated[
        None | str | Filter6,
        Field(
            None,
            description="Source of the reimbursement (ex. FSU Law School).",
        ),
    ]
    purpose: Annotated[
        None | str | Filter6,
        Field(
            None,
            description="Purpose of the reimbursement (ex. Baseball announcer).",
        ),
    ]
    items_paid_or_provided: Annotated[
        None | str | Filter6,
        Field(
            None,
            description="Items reimbursed (ex. Room, Airfare).",
        ),
    ]
    financial_disclosure: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            description="The financial disclosure associated with this reimbursement.",
            json_schema_extra={
                "related_class_name": "FinancialDisclosuresEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]


