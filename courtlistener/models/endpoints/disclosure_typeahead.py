from typing import ClassVar

from courtlistener.models.endpoint import Endpoint


class DisclosureTypeaheadEndpoint(Endpoint):
    """Disclosure Typeahead Endpoint"""

    endpoint: ClassVar[str] = "/disclosure-typeahead/"
    endpoint_id: ClassVar[str] = "disclosure-typeahead"
    endpoint_name: ClassVar[str] = "Disclosure Typeahead"
