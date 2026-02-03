from typing import ClassVar

from courtlistener.models.endpoint import Endpoint


class BankruptcyInformationEndpoint(Endpoint):
    """Bankruptcy Information Endpoint"""

    endpoint: ClassVar[str] = "/bankruptcy-information/"
    endpoint_id: ClassVar[str] = "bankruptcy-information"
    endpoint_name: ClassVar[str] = "Bankruptcy Information"
