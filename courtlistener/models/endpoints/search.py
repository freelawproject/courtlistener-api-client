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


class SearchEndpoint(Endpoint):
    """Search Endpoint"""

    endpoint: ClassVar[str] = "/search/"
    endpoint_id: ClassVar[str] = "search"
    endpoint_name: ClassVar[str] = "Search"



