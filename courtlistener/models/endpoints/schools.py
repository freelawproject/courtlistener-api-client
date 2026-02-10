from datetime import datetime
from typing import Annotated, Any, ClassVar

from pydantic import BeforeValidator, Field

from courtlistener.models.endpoint import Endpoint
from courtlistener.models.filters import Filter6, Filter8
from courtlistener.utils import (
    related_validator,
)


class SchoolsEndpoint(Endpoint):
    """Schools Endpoint"""

    endpoint: ClassVar[str] = "/schools/"
    endpoint_id: ClassVar[str] = "schools"
    endpoint_name: ClassVar[str] = "Schools"

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
    name: Annotated[
        None | str | Filter6,
        Field(
            None,
            description="The name of the school or alias",
        ),
    ]
    ein: Annotated[
        None | int,
        Field(
            None,
            description="The EIN assigned by the IRS",
        ),
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
