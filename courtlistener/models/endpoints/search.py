from typing import ClassVar

from courtlistener.models.endpoint import Endpoint


class SearchEndpoint(Endpoint):
    """Search Endpoint"""

    endpoint: ClassVar[str] = "/search/"
    endpoint_id: ClassVar[str] = "search"
    endpoint_name: ClassVar[str] = "Search"
