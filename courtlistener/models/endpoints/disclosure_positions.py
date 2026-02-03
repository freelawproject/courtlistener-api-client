from datetime import datetime
from typing import Annotated, Any, ClassVar

from pydantic import BeforeValidator, Field

from courtlistener.models.endpoint import Endpoint
from courtlistener.models.filters import Filter6, Filter8
from courtlistener.utils import (
    related_validator,
)


class DisclosurePositionsEndpoint(Endpoint):
    """Disclosure Positions Endpoint"""

    endpoint: ClassVar[str] = "/disclosure-positions/"
    endpoint_id: ClassVar[str] = "disclosure-positions"
    endpoint_name: ClassVar[str] = "Disclosure Positions"

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
            description="Does the position row contain redaction(s)?",
        ),
    ]
    position: Annotated[
        None | str | Filter6,
        Field(
            None,
            description="Position title (ex. Trustee).",
        ),
    ]
    organization_name: Annotated[
        None | str | Filter6,
        Field(
            None,
            description="Name of organization or entity (ex. Trust #1).",
        ),
    ]
    financial_disclosure: Annotated[
        None | dict[str, Any] | int,
        Field(
            None,
            description="The financial disclosure associated with this financial position.",
            json_schema_extra={
                "related_class_name": "FinancialDisclosuresEndpoint",
            },
        ),
        BeforeValidator(related_validator),
    ]
