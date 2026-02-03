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


class DisclosureTypeaheadEndpoint(Endpoint):
    """Disclosure Typeahead Endpoint"""

    endpoint: ClassVar[str] = "/disclosure-typeahead/"
    endpoint_id: ClassVar[str] = "disclosure-typeahead"
    endpoint_name: ClassVar[str] = "Disclosure Typeahead"



