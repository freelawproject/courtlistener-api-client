from typing import ClassVar

from courtlistener.models.endpoint import Endpoint


class TagEndpoint(Endpoint):
    """Tag Endpoint"""

    endpoint: ClassVar[str] = "/tag/"
    endpoint_id: ClassVar[str] = "tag"
    endpoint_name: ClassVar[str] = "Tag"
