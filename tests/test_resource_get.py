"""Unit tests for `Resource.get` id handling.

JSON clients often send integral floats (5.0) for integer ids; the
filter path already coerces these via the pydantic endpoint models, so
`get` matches that tolerance when building the URL.
"""

from unittest.mock import MagicMock

from courtlistener.models import ENDPOINTS
from courtlistener.resource import Resource


class TestGetIdNormalization:
    def _requested_path(self, id):
        client = MagicMock()
        client._request = MagicMock(return_value={})
        Resource(client, ENDPOINTS["dockets"]).get(id)
        return client._request.call_args.args[1]

    def test_integral_float_is_normalized(self):
        assert self._requested_path(5.0).endswith("/5/")

    def test_int_passes_through(self):
        assert self._requested_path(5).endswith("/5/")

    def test_str_passes_through(self):
        assert self._requested_path("scotus").endswith("/scotus/")

    def test_non_integral_float_is_left_alone(self):
        # Garbage in, garbage out: the API's 404 is the error surface.
        assert self._requested_path(5.5).endswith("/5.5/")
