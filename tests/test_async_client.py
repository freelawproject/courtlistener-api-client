"""Tests for AsyncCourtListener and sync/async API parity."""

import inspect

import pytest

from courtlistener import AsyncCourtListener, CourtListener
from courtlistener.async_client.alerts import (
    AsyncDocketAlerts,
    AsyncSearchAlerts,
)
from courtlistener.async_client.citation_lookup import AsyncCitationLookup
from courtlistener.async_client.resource import (
    AsyncResource,
    AsyncResourceIterator,
)
from courtlistener.sync_client.alerts import DocketAlerts, SearchAlerts
from courtlistener.sync_client.citation_lookup import CitationLookup
from courtlistener.sync_client.resource import Resource, ResourceIterator

# Sync members that are intentionally renamed in the async API. Both
# clients expose ``get_*`` methods for the lazy accessors; the sync
# property forms are deprecated backwards-compat aliases that collapse
# onto the same methods here. close/context management follows the
# httpx ``aclose``/``__aenter__`` convention.
RENAMES = {
    CourtListener: {"close": "aclose"},
    ResourceIterator: {
        "current_page": "get_current_page",
        "count": "get_count",
        "document_count": "get_document_count",
        "results": "get_results",
    },
}

PAIRS = [
    (CourtListener, AsyncCourtListener),
    (Resource, AsyncResource),
    (ResourceIterator, AsyncResourceIterator),
    (SearchAlerts, AsyncSearchAlerts),
    (DocketAlerts, AsyncDocketAlerts),
    (CitationLookup, AsyncCitationLookup),
]


def _public_members(cls):
    return {name for name in vars(cls) if not name.startswith("_")}


def _param_facts(func):
    """Parameter (name, kind, default) triples for a function."""
    return [
        (param.name, param.kind, param.default)
        for param in inspect.signature(func).parameters.values()
    ]


SELF_ONLY = [
    ("self", inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.empty)
]


class TestSyncAsyncParity:
    """Guardrails for keeping the two clients aligned (see unasync plan)."""

    @pytest.mark.parametrize(
        "sync_cls,async_cls", PAIRS, ids=lambda c: c.__name__
    )
    def test_public_api_surface_matches(self, sync_cls, async_cls):
        renames = RENAMES.get(sync_cls, {})
        expected = {
            renames.get(name, name) for name in _public_members(sync_cls)
        }
        assert _public_members(async_cls) == expected

    def test_context_manager_protocols(self):
        assert hasattr(CourtListener, "__enter__")
        assert hasattr(CourtListener, "__exit__")
        assert hasattr(AsyncCourtListener, "__aenter__")
        assert hasattr(AsyncCourtListener, "__aexit__")
        assert not hasattr(AsyncCourtListener, "__enter__")

    def test_iterator_protocols(self):
        assert hasattr(ResourceIterator, "__iter__")
        assert hasattr(AsyncResourceIterator, "__aiter__")
        assert not hasattr(AsyncResourceIterator, "__iter__")

    def test_io_methods_are_coroutines(self):
        for method in (
            AsyncCourtListener._request,
            AsyncCourtListener.aclose,
            AsyncResource.get,
            AsyncResourceIterator.get_current_page,
            AsyncResourceIterator.get_count,
            AsyncResourceIterator.get_results,
            AsyncResourceIterator.get_document_count,
            AsyncResourceIterator.dump,
            AsyncResourceIterator.next,
            AsyncResourceIterator.previous,
            AsyncResourceIterator.has_next,
            AsyncResourceIterator.has_previous,
            AsyncSearchAlerts.create,
            AsyncDocketAlerts.subscribe,
            AsyncCitationLookup.lookup_text,
        ):
            assert inspect.iscoroutinefunction(method), method

    def test_list_is_not_a_coroutine(self):
        """list() performs no I/O in either client."""
        assert not inspect.iscoroutinefunction(AsyncResource.list)

    @pytest.mark.parametrize(
        "sync_cls,async_cls", PAIRS, ids=lambda c: c.__name__
    )
    def test_signatures_match(self, sync_cls, async_cls):
        """Shared public methods take identical arguments.

        Compares parameter name, kind, and default (not annotations,
        which legitimately differ between flavors). Sync properties
        renamed to awaitable ``get_*`` methods must take no arguments;
        non-renamed sync properties must stay properties in async.
        """
        renames = RENAMES.get(sync_cls, {})
        for name in _public_members(sync_cls):
            sync_attr = inspect.getattr_static(sync_cls, name)
            async_attr = inspect.getattr_static(
                async_cls, renames.get(name, name)
            )
            if isinstance(sync_attr, property):
                if name in renames:
                    assert inspect.iscoroutinefunction(async_attr), name
                    assert _param_facts(async_attr) == SELF_ONLY, name
                else:
                    assert isinstance(async_attr, property), name
                continue
            if isinstance(sync_attr, classmethod):
                sync_attr = sync_attr.__func__
                async_attr = async_attr.__func__
            if not inspect.isfunction(sync_attr):
                continue
            assert _param_facts(sync_attr) == _param_facts(async_attr), name

    def test_duplicated_citation_helpers_are_identical(self):
        """The pure helpers are deliberately duplicated per flavor.

        Until the sync side is generated with unasync, keep the copies
        byte-identical so they can't drift.
        """
        import courtlistener.async_client.citation_lookup as async_mod
        import courtlistener.sync_client.citation_lookup as sync_mod

        for name in ("parse_wait_until", "_wait_until_seconds", "_split_text"):
            assert inspect.getsource(
                getattr(sync_mod, name)
            ) == inspect.getsource(getattr(async_mod, name)), name
        for name in (
            "MAX_TEXT_LENGTH",
            "THROTTLE_STATUS",
            "MAX_RETRY_WAIT_SECONDS",
        ):
            assert getattr(sync_mod, name) == getattr(async_mod, name), name


class TestAsyncClientConstruction:
    def test_requires_authentication(self, monkeypatch):
        monkeypatch.delenv("COURTLISTENER_API_TOKEN", raising=False)
        with pytest.raises(ValueError, match="Authentication is required"):
            AsyncCourtListener()

    def test_env_var_token(self, monkeypatch):
        monkeypatch.setenv("COURTLISTENER_API_TOKEN", "env-token")
        cl = AsyncCourtListener()
        assert cl.api_token == "env-token"

    def test_access_token_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("COURTLISTENER_API_TOKEN", "env-token")
        cl = AsyncCourtListener(access_token="oauth")
        assert cl.access_token == "oauth"
        assert cl.api_token is None
        assert cl.client.headers["Authorization"] == "Bearer oauth"

    def test_api_token_header(self):
        cl = AsyncCourtListener(api_token="tok")
        assert cl.client.headers["Authorization"] == "Token tok"

    def test_resource_accessors_are_cached(self):
        cl = AsyncCourtListener(api_token="tok")
        resource = cl.courts
        assert isinstance(resource, AsyncResource)
        assert cl.courts is resource

    def test_unknown_attribute_raises(self):
        cl = AsyncCourtListener(api_token="tok")
        with pytest.raises(AttributeError):
            _ = cl.not_an_endpoint

    def test_addon_accessors(self):
        cl = AsyncCourtListener(api_token="tok")
        assert isinstance(cl.alerts, AsyncSearchAlerts)
        assert isinstance(cl.docket_alerts, AsyncDocketAlerts)
        assert isinstance(cl.citation_lookup, AsyncCitationLookup)

    @pytest.mark.asyncio
    async def test_context_manager_closes_client(self):
        async with AsyncCourtListener(api_token="tok") as cl:
            http_client = cl.client
            assert not http_client.is_closed
        assert cl._http_client is None
        assert http_client.is_closed

    @pytest.mark.asyncio
    async def test_aclose_without_client_is_noop(self):
        cl = AsyncCourtListener(api_token="tok")
        await cl.aclose()
        assert cl._http_client is None
