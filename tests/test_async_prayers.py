"""Unit tests for AsyncPrayers."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from courtlistener.async_client.prayers import AsyncPrayers

pytestmark = pytest.mark.asyncio


def _mock_client(*responses):
    client = MagicMock()
    client._request = AsyncMock(side_effect=list(responses) or None)
    return client


class TestPrayers:
    async def test_create_posts_recap_document(self):
        client = _mock_client({"id": 1, "recap_document": 112, "status": 1})
        prayers = AsyncPrayers(client)
        result = await prayers.create(recap_document=112)

        method, path = client._request.await_args.args
        assert method == "POST"
        assert path.endswith("/prayers/")
        assert client._request.await_args.kwargs["json"] == {
            "recap_document": 112
        }
        assert result["id"] == 1

    async def test_create_rejects_non_int(self):
        prayers = AsyncPrayers(_mock_client())
        with pytest.raises(ValidationError):
            await prayers.create(recap_document="not-an-id")

    async def test_delete(self):
        client = _mock_client({})
        prayers = AsyncPrayers(client)
        await prayers.delete(3)
        method, path = client._request.await_args.args
        assert method == "DELETE"
        assert path.endswith("/prayers/3/")
