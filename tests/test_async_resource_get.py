"""Unit tests for `AsyncResource.get` id handling.

JSON clients often send integral floats (5.0) for integer ids; the
filter path already coerces these via the pydantic endpoint models, so
`get` matches that tolerance when building the URL.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from courtlistener.async_client.resource import AsyncResource
from courtlistener.models import ENDPOINTS

pytestmark = pytest.mark.asyncio


class TestGetIdNormalization:
    async def _requested_path(self, id):
        client = MagicMock()
        client._request = AsyncMock(return_value={})
        await AsyncResource(client, ENDPOINTS["dockets"]).get(id)
        return client._request.await_args.args[1]

    async def test_integral_float_is_normalized(self):
        assert (await self._requested_path(5.0)).endswith("/5/")

    async def test_int_passes_through(self):
        assert (await self._requested_path(5)).endswith("/5/")

    async def test_str_passes_through(self):
        assert (await self._requested_path("scotus")).endswith("/scotus/")

    async def test_non_integral_float_is_left_alone(self):
        # Garbage in, garbage out: the API's 404 is the error surface.
        assert (await self._requested_path(5.5)).endswith("/5.5/")
