from typing import ClassVar

from courtlistener.models.endpoint import Endpoint


class OriginatingCourtInformationEndpoint(Endpoint):
    """Originating Court Information Endpoint"""

    endpoint: ClassVar[str] = "/originating-court-information/"
    endpoint_id: ClassVar[str] = "originating-court-information"
    endpoint_name: ClassVar[str] = "Originating Court Information"
