from typing import Annotated, ClassVar

from pydantic import BeforeValidator, Field

from courtlistener.models.endpoint import Endpoint
from courtlistener.utils import (
    choice_validator,
)


class DocketAlertsEndpoint(Endpoint):
    """Docket Alerts Endpoint"""

    endpoint: ClassVar[str] = "/docket-alerts/"
    endpoint_id: ClassVar[str] = "docket-alerts"
    endpoint_name: ClassVar[str] = "Docket Alerts"

    id: Annotated[
        None | int,
        Field(
            None,
        ),
    ]
    alert_type: Annotated[
        None | int,
        Field(
            None,
            description="The subscription type assigned, Unsubscription or Subscription.",
            json_schema_extra={
                "choices": [
                    {"value": 0, "display_name": "Unsubscription"},
                    {"value": 1, "display_name": "Subscription"},
                ],
            },
        ),
        BeforeValidator(choice_validator),
    ]
    docket: Annotated[
        None | int,
        Field(
            None,
            description="The docket that we are subscribed to.",
        ),
    ]
