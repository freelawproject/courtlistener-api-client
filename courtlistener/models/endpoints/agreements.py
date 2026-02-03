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


class AgreementsEndpoint(Endpoint):
    """Agreements Endpoint"""

    endpoint: ClassVar[str] = "/agreements/"
    endpoint_id: ClassVar[str] = "agreements"
    endpoint_name: ClassVar[str] = "Agreements"

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
            description="Does the agreement row contain redaction(s)?",
        ),
    ]
    parties_and_terms: Annotated[
        None | str | Filter6,
        Field(
            None,
            description="Parties and terms of agreement (ex. Board Member NY Ballet)",
        ),
    ]
    date_raw: Annotated[
        None | str | Filter6,
        Field(
            None,
            description="Date of judicial agreement.",
        ),
    ]
    financial_disclosure: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            description="The financial disclosure associated with this agreement.",
            json_schema_extra={
                "related_class_name": "FinancialDisclosuresEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]


