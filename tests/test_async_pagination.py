"""Unit tests for AsyncResourceIterator pagination behavior."""

from unittest.mock import AsyncMock

import pytest

from courtlistener import AsyncCourtListener
from courtlistener.async_client.resource import AsyncResourceIterator

pytestmark = pytest.mark.asyncio

NEXT_URL = "https://www.courtlistener.com/api/rest/v4/courts/?cursor=abc"


def _page(results, next=None, previous=None, count=None):
    return {
        "count": count if count is not None else len(results),
        "next": next,
        "previous": previous,
        "results": results,
    }


def _iterator(pages) -> AsyncResourceIterator:
    cl = AsyncCourtListener(api_token="tok")
    cl._request = AsyncMock(side_effect=pages)
    return cl.courts.list()


class TestCurrentPage:
    async def test_fetches_first_page(self):
        it = _iterator([_page([{"id": "scotus"}])])
        page = await it.get_current_page()
        assert page.results == [{"id": "scotus"}]

    async def test_page_is_cached(self):
        it = _iterator([_page([{"id": "scotus"}])])
        first = await it.get_current_page()
        second = await it.get_current_page()
        assert first is second
        assert it._client._request.await_count == 1

    async def test_results_shortcut(self):
        it = _iterator([_page([{"id": "scotus"}])])
        assert await it.get_results() == [{"id": "scotus"}]


class TestNavigation:
    async def test_has_next(self):
        it = _iterator([_page([{"id": 1}], next=NEXT_URL)])
        assert await it.has_next()

    async def test_no_next(self):
        it = _iterator([_page([{"id": 1}])])
        assert not await it.has_next()

    async def test_next_fetches_next_url(self):
        it = _iterator(
            [
                _page([{"id": 1}], next=NEXT_URL),
                _page([{"id": 2}], previous="prev"),
            ]
        )
        await it.next()
        assert await it.get_results() == [{"id": 2}]
        method, path = it._client._request.await_args_list[1].args
        assert method == "GET"
        assert path == "/api/rest/v4/courts/?cursor=abc"

    async def test_next_raises_without_next_page(self):
        it = _iterator([_page([{"id": 1}])])
        with pytest.raises(ValueError, match="No next page"):
            await it.next()

    async def test_previous_raises_on_first_page(self):
        it = _iterator([_page([{"id": 1}])])
        assert not await it.has_previous()
        with pytest.raises(ValueError, match="No previous page"):
            await it.previous()


class TestIteration:
    async def test_iterates_across_pages(self):
        it = _iterator(
            [
                _page([{"id": 1}, {"id": 2}], next=NEXT_URL),
                _page([{"id": 3}]),
            ]
        )
        items = [item async for item in it]
        assert [item["id"] for item in items] == [1, 2, 3]

    async def test_iteration_respects_result_index(self):
        it = _iterator([_page([{"id": 1}, {"id": 2}, {"id": 3}])])
        collected = []
        async for item in it:
            collected.append(item)
            if len(collected) == 2:
                break
        assert [item["id"] async for item in it] == [3]


class TestCount:
    async def test_integer_count(self):
        it = _iterator([_page([{"id": 1}], count=42)])
        assert await it.get_count() == 42

    async def test_count_url_is_fetched(self):
        count_url = (
            "https://www.courtlistener.com/api/rest/v4/courts/?count=on"
        )
        it = _iterator(
            [
                _page([{"id": 1}], count=count_url),
                {"count": 99},
            ]
        )
        assert await it.get_count() == 99
        method, path = it._client._request.await_args_list[1].args
        assert path == "/api/rest/v4/courts/?count=on"

    async def test_count_is_cached(self):
        it = _iterator([_page([{"id": 1}], count=42)])
        await it.get_count()
        await it.get_count()
        assert it._client._request.await_count == 1

    async def test_missing_count_raises(self):
        it = _iterator([_page([{"id": 1}], count=-1) | {"count": None}])
        with pytest.raises(ValueError, match="No count URL"):
            await it.get_count()


class TestDumpLoad:
    async def test_round_trip_uses_cached_page(self):
        it = _iterator([_page([{"id": 1}], count=7)])
        await it.get_count()
        state = await it.dump()

        restored_client = AsyncCourtListener(api_token="tok")
        restored_client._request = AsyncMock()
        restored = AsyncResourceIterator.load(restored_client, state)

        assert await restored.get_results() == [{"id": 1}]
        assert await restored.get_count() == 7
        restored_client._request.assert_not_awaited()

    async def test_dump_preserves_position(self):
        it = _iterator([_page([{"id": 1}, {"id": 2}])])
        collected = []
        async for item in it:
            collected.append(item)
            if len(collected) == 1:
                break
        state = await it.dump()
        assert state["page_result_index"] == 1
