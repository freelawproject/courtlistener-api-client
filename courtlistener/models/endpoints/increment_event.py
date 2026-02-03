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


class IncrementEventEndpoint(Endpoint):
    """Increment Event Endpoint"""

    endpoint: ClassVar[str] = "/increment-event/"
    endpoint_id: ClassVar[str] = "increment-event"
    endpoint_name: ClassVar[str] = "Increment Event"



