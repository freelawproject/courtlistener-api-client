"""Unit tests for AsyncTags and AsyncDocketTags."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from courtlistener.async_client.docket_tags import AsyncDocketTags
from courtlistener.async_client.tags import AsyncTags

pytestmark = pytest.mark.asyncio

TAG = {"id": 5, "name": "patents", "published": False}
DOCKET_TAG = {"id": 9, "tag": 5, "docket": 123}


def _mock_client(*responses):
    client = MagicMock()
    client._request = AsyncMock(side_effect=list(responses) or None)
    return client


class TestTags:
    async def test_create_posts_only_the_fields_given(self):
        client = _mock_client(TAG)
        result = await AsyncTags(client).create(
            name="patents", published=False
        )

        method, path = client._request.await_args.args
        assert method == "POST"
        assert path.endswith("/tags/")
        assert client._request.await_args.kwargs["json"] == {
            "name": "patents",
            "published": False,
        }
        assert result == TAG

    @pytest.mark.parametrize("name", ["two words", "slash/name", "", "x" * 51])
    async def test_create_rejects_names_that_are_not_slugs(self, name):
        client = _mock_client()
        with pytest.raises(ValidationError):
            await AsyncTags(client).create(name=name)
        client._request.assert_not_awaited()

    async def test_update_patches_only_the_fields_given(self):
        client = _mock_client(TAG)
        await AsyncTags(client).update(5, title="Patent cases")

        method, path = client._request.await_args.args
        assert method == "PATCH"
        assert path.endswith("/tags/5/")
        assert client._request.await_args.kwargs["json"] == {
            "title": "Patent cases"
        }

    async def test_update_validates_the_name(self):
        client = _mock_client()
        with pytest.raises(ValidationError):
            await AsyncTags(client).update(5, name="two words")
        client._request.assert_not_awaited()

    async def test_update_rejects_unknown_fields(self):
        client = _mock_client()
        with pytest.raises(ValidationError):
            await AsyncTags(client).update(5, user=1)
        client._request.assert_not_awaited()

    async def test_delete(self):
        client = _mock_client({})
        await AsyncTags(client).delete(5)
        method, path = client._request.await_args.args
        assert method == "DELETE"
        assert path.endswith("/tags/5/")


class TestDocketTags:
    async def test_create_posts_tag_and_docket(self):
        client = _mock_client(DOCKET_TAG)
        result = await AsyncDocketTags(client).create(tag=5, docket=123)

        method, path = client._request.await_args.args
        assert method == "POST"
        assert path.endswith("/docket-tags/")
        assert client._request.await_args.kwargs["json"] == {
            "tag": 5,
            "docket": 123,
        }
        assert result == DOCKET_TAG

    async def test_create_rejects_non_int(self):
        client = _mock_client()
        with pytest.raises(ValidationError):
            await AsyncDocketTags(client).create(tag="patents", docket=123)
        client._request.assert_not_awaited()

    async def test_delete(self):
        client = _mock_client({})
        await AsyncDocketTags(client).delete(9)
        method, path = client._request.await_args.args
        assert method == "DELETE"
        assert path.endswith("/docket-tags/9/")
