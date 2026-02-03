from typing import Annotated, ClassVar

from pydantic import BeforeValidator, Field

from courtlistener.models.endpoint import Endpoint
from courtlistener.models.filters import Filter4
from courtlistener.utils import (
    choice_validator,
)


class AlertsEndpoint(Endpoint):
    """Alerts Endpoint"""

    endpoint: ClassVar[str] = "/alerts/"
    endpoint_id: ClassVar[str] = "alerts"
    endpoint_name: ClassVar[str] = "Alerts"

    id: Annotated[
        None | int,
        Field(
            None,
        ),
    ]
    name: Annotated[
        None | str | Filter4,
        Field(
            None,
        ),
    ]
    query: Annotated[
        None | str | Filter4,
        Field(
            None,
        ),
    ]
    rate: Annotated[
        None | str,
        Field(
            None,
            json_schema_extra={
                "choices": [
                    {"value": "rt", "display_name": "Real Time"},
                    {"value": "dly", "display_name": "Daily"},
                    {"value": "wly", "display_name": "Weekly"},
                    {"value": "mly", "display_name": "Monthly"},
                    {"value": "off", "display_name": "Off"},
                ],
            },
        ),
        BeforeValidator(choice_validator),
    ]
