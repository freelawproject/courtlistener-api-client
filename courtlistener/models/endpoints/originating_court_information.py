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


class OriginatingCourtInformationEndpoint(Endpoint):
    """Originating Court Information Endpoint"""

    endpoint: ClassVar[str] = "/originating-court-information/"
    endpoint_id: ClassVar[str] = "originating-court-information"
    endpoint_name: ClassVar[str] = "Originating Court Information"



