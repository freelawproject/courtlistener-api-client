import os

DEFAULT_API_BASE_URL = "https://www.courtlistener.com/api/rest/v4"


def get_api_base_url() -> str:
    """Return the CourtListener REST API root, without a trailing slash."""
    return (
        os.environ.get("COURTLISTENER_API_BASE_URL") or DEFAULT_API_BASE_URL
    ).rstrip("/")
