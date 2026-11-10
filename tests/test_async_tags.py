"""Unit tests for AsyncTags and AsyncDocketTags."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from courtlistener.async_client.tags import AsyncDocketTags, AsyncTags

pytestmark = pytest.mark.asyncio

TAG = {"id": 5, "name": "patents", "published": False}
DOCKET_TAG = {"id": 9, "tag": 5, "docket": 123}


def _mock_client(*responses):
    client = MagicMock()
    client._request = AsyncMock(side_effect=list(responses) or None)
    return client


async def _aiter(items):
    for item in items:
        yield item


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

    async def test_update_patches_the_tag(self):
        client = _mock_client(TAG)
        await AsyncTags(client).update(5, title="Patent cases")

        method, path = client._request.await_args.args
        assert method == "PATCH"
        assert path.endswith("/tags/5/")
        assert client._request.await_args.kwargs["json"] == {
            "title": "Patent cases"
        }

    async def test_update_rejects_unknown_fields(self):
        with pytest.raises(ValidationError):
            await AsyncTags(_mock_client()).update(5, user=1)

    async def test_delete(self):
        client = _mock_client({})
        await AsyncTags(client).delete(5)
        method, path = client._request.await_args.args
        assert method == "DELETE"
        assert path.endswith("/tags/5/")


class TestDocketTags:
    async def test_create_posts_tag_and_docket(self):
        client = _mock_client(DOCKET_TAG)
        await AsyncDocketTags(client).create(tag=5, docket=123)

        method, path = client._request.await_args.args
        assert method == "POST"
        assert path.endswith("/docket-tags/")
        assert client._request.await_args.kwargs["json"] == {
            "tag": 5,
            "docket": 123,
        }

    async def test_delete(self):
        client = _mock_client({})
        await AsyncDocketTags(client).delete(9)
        method, path = client._request.await_args.args
        assert method == "DELETE"
        assert path.endswith("/docket-tags/9/")

    async def test_add_creates_when_absent(self):
        docket_tags = AsyncDocketTags(_mock_client())
        docket_tags.list = MagicMock(return_value=_aiter([]))
        docket_tags.create = AsyncMock(return_value=DOCKET_TAG)

        assert await docket_tags.add(5, 123) == DOCKET_TAG
        docket_tags.list.assert_called_once_with(tag=5, docket=123)
        docket_tags.create.assert_awaited_once_with(5, 123)

    async def test_add_returns_existing(self):
        docket_tags = AsyncDocketTags(_mock_client())
        docket_tags.list = MagicMock(return_value=_aiter([DOCKET_TAG]))
        docket_tags.create = AsyncMock()

        result = await docket_tags.add(5, 123)
        assert result == {**DOCKET_TAG, "already_tagged": True}
        docket_tags.create.assert_not_awaited()

    async def test_remove_deletes_by_docket_tag_id(self):
        docket_tags = AsyncDocketTags(_mock_client())
        docket_tags.list = MagicMock(return_value=_aiter([DOCKET_TAG]))
        docket_tags.delete = AsyncMock()

        await docket_tags.remove(5, 123)
        docket_tags.list.assert_called_once_with(tag=5, docket=123)
        docket_tags.delete.assert_awaited_once_with(9)

    async def test_remove_raises_when_absent(self):
        docket_tags = AsyncDocketTags(_mock_client())
        docket_tags.list = MagicMock(return_value=_aiter([]))

        with pytest.raises(ValueError):
            await docket_tags.remove(5, 123)
