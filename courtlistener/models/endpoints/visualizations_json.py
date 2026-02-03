from typing import ClassVar

from courtlistener.models.endpoint import Endpoint


class VisualizationsJsonEndpoint(Endpoint):
    """Visualizations/Json Endpoint"""

    endpoint: ClassVar[str] = "/visualizations/json/"
    endpoint_id: ClassVar[str] = "visualizations/json"
    endpoint_name: ClassVar[str] = "Visualizations/Json"
