import os
import sys
from unittest.mock import MagicMock

import httpx
import pytest
from dotenv import load_dotenv

from courtlistener import CourtListener
from courtlistener.mcp.transport import set_pool

# Stub native-build MCP deps only when they are not installed, so
# tests that don't need them (e.g. test_auth) can still be collected.
# When the real packages ARE installed, they are used as-is.
for _mod in ("eyecite", "eyecite.models", "tiktoken"):
    try:
        __import__(_mod)
    except ImportError:
        sys.modules[_mod] = MagicMock()

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


class RecordingTransport(httpx.MockTransport):
    """A mock pool that remembers whether it was closed."""

    closed = False

    async def aclose(self):
        self.closed = True


@pytest.fixture(autouse=True)
def reset_mcp_pool():
    """Drop the MCP server's shared connection pool after each test."""
    yield
    set_pool(None)


@pytest.fixture
def mock_http():
    """Route the MCP server's shared connection pool to a handler.

    Call it with ``handler(request) -> httpx.Response``; it returns the
    list the sent requests are recorded in.
    """

    def install(handler):
        requests: list[httpx.Request] = []

        def record(request):
            requests.append(request)
            return handler(request)

        set_pool(RecordingTransport(record))
        return requests

    return install


def first_result_id(results):
    """Extract the ID from the first result in a ResourceIterator."""
    if results.get_results():
        result = results.get_results()[0]
        return result.get("id") or result.get("resource_uri")
    return None
