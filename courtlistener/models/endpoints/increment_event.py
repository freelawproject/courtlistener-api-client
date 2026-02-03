from typing import ClassVar

from courtlistener.models.endpoint import Endpoint


class IncrementEventEndpoint(Endpoint):
    """Increment Event Endpoint"""

    endpoint: ClassVar[str] = "/increment-event/"
    endpoint_id: ClassVar[str] = "increment-event"
    endpoint_name: ClassVar[str] = "Increment Event"
