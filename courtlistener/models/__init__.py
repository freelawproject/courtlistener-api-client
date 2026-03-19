import logging

from courtlistener.models.endpoint import Endpoint
from courtlistener.models.page import Page

try:
    from courtlistener.models.endpoints import ENDPOINTS
    from courtlistener.models.filters import FILTERS
except Exception as exc:
    logging.warning(
        f"Error importing filters and endpoints: {exc}\n"
        "You may need to run `scripts/generate_models.py` to generate them."
    )
    ENDPOINTS = {}
    FILTERS = {}


__all__ = [
    "Endpoint",
    "Page",
    "FILTERS",
    "ENDPOINTS",
]
