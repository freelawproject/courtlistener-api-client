import os

import pytest
from dotenv import load_dotenv

from courtlistener import CourtListener

load_dotenv()


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: mark test as integration test (hits real API)",
    )


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests that hit the real API",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-integration"):
        return
    skip = pytest.mark.skip(reason="need --run-integration to run")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def client():
    """Real CourtListener client for integration tests.

    Requires COURTLISTENER_API_TOKEN to be set.
    """
    token = os.environ.get("COURTLISTENER_API_TOKEN")
    if not token:
        pytest.skip("COURTLISTENER_API_TOKEN not set")
    with CourtListener(api_token=token) as cl:
        yield cl


def first_result_id(results):
    """Extract the ID from the first result in a ResourceIterator."""
    if results.results:
        result = results.results[0]
        return result.get("id") or result.get("resource_uri")
    return None
