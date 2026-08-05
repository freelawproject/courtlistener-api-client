"""Tests for the Session abstraction: the in-memory backend, the
Redis/in-memory fallback in ``get_session``, and the domain methods
shared by both backends.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from courtlistener import CourtListener
from courtlistener.mcp.session import (
    InMemorySession,
    RedisSession,
    Session,
    get_session,
    set_session,
    token_info_key,
)


@pytest.fixture(autouse=True)
def reset_session_singleton():
    """Isolate the module-level singleton between tests."""
    set_session(None)
    yield
    set_session(None)


@pytest.fixture
def client():
    return CourtListener(api_token="test-token")


def run(coro):
    return asyncio.run(coro)


class TestInMemorySession:
    def test_get_missing_key_returns_none(self):
        session = InMemorySession()
        assert run(session._get("nope")) is None

    def test_set_get_roundtrip(self):
        session = InMemorySession()
        run(session._set("key", "value", 60))
        assert run(session._get("key")) == "value"

    def test_delete(self):
        session = InMemorySession()
        run(session._set("key", "value", 60))
        run(session._delete("key"))
        assert run(session._get("key")) is None

    def test_delete_missing_key_is_noop(self):
        session = InMemorySession()
        run(session._delete("nope"))

    def test_expired_entry_returns_none_and_is_dropped(self):
        import time

        session = InMemorySession()
        run(session._set("key", "value", 60))
        # Rewind the stored expiry to simulate the TTL elapsing.
        value, _ = session._data["key"]
        session._data["key"] = (value, time.monotonic() - 1)
        assert run(session._get("key")) is None
        assert "key" not in session._data

    def test_set_applies_ttl(self):
        import time

        session = InMemorySession()
        before = time.monotonic()
        run(session._set("key", "value", 60))
        _, expires_at = session._data["key"]
        assert before + 59 < expires_at <= time.monotonic() + 60


class TestSessionDomainMethods:
    """Domain methods run against the in-memory backend, exercising the
    shared key layout and JSON round-trip on the base class."""

    def test_query_roundtrip(self, client):
        session = InMemorySession()
        run(session.store_query("abc123", {"response": {"x": 1}}, client))
        assert run(session.get_query("abc123", client)) == {
            "response": {"x": 1}
        }

    def test_query_missing_returns_none(self, client):
        session = InMemorySession()
        assert run(session.get_query("nope", client)) is None

    def test_queries_are_user_scoped(self, client):
        session = InMemorySession()
        other = CourtListener(api_token="other-token")
        run(session.store_query("abc123", {"response": 1}, client))
        assert run(session.get_query("abc123", other)) is None

    def test_citation_analysis_roundtrip(self, client):
        session = InMemorySession()
        run(session.store_citation_analysis("job1", {"pending": []}, client))
        assert run(session.get_citation_analysis("job1", client)) == {
            "pending": []
        }

    def test_document_cache_roundtrip(self):
        session = InMemorySession()
        run(session.store_document("opinion", 42, "full text"))
        assert run(session.get_document("opinion", 42)) == "full text"

    def test_document_cache_is_not_user_scoped(self):
        session = InMemorySession()
        run(session.store_document("opinion", 42, "full text"))
        # No client/user involved in the key at all.
        assert run(session._get("mcp:doc:opinion:42")) == "full text"

    def test_token_cache_roundtrip_and_invalidate(self):
        session = InMemorySession()
        info = {"user_hash": "hash123"}
        run(session.store_token_info("tok", "oauth", info))
        assert run(session.get_token_info("tok", "oauth")) == info
        run(session.invalidate_token("tok", "oauth"))
        assert run(session.get_token_info("tok", "oauth")) is None

    def test_token_info_survives_a_json_roundtrip(self):
        """The cache holds a structured record rather than a bare hash,
        so it has room for more than ``user_hash`` later."""
        session = InMemorySession()
        info = {"user_hash": "hash123", "extra": ["a", 1, None]}
        run(session.store_token_info("tok", "oauth", info))
        raw = run(session._get(token_info_key("tok", "oauth")))
        assert json.loads(raw) == info
        assert run(session.get_token_info("tok", "oauth")) == info

    def test_token_cache_does_not_cross_credential_kinds(self):
        """An entry verified as one kind must never satisfy a lookup for
        another — otherwise one valid request would warm a cache entry
        that a different credential type could then ride in on."""
        session = InMemorySession()
        run(session.store_token_info("tok", "oauth", {"user_hash": "h"}))
        assert run(session.get_token_info("tok", "api_token")) is None
        assert run(session.get_token_info("tok", "oauth")) is not None

    def test_invalidating_one_kind_leaves_the_other(self):
        session = InMemorySession()
        run(session.store_token_info("tok", "oauth", {"user_hash": "h1"}))
        run(session.store_token_info("tok", "api_token", {"user_hash": "h2"}))
        run(session.invalidate_token("tok", "oauth"))
        assert run(session.get_token_info("tok", "oauth")) is None
        assert run(session.get_token_info("tok", "api_token")) == {
            "user_hash": "h2"
        }

    def test_token_never_stored_in_plaintext(self):
        session = InMemorySession()
        run(
            session.store_token_info(
                "secret-token", "oauth", {"user_hash": "hash123"}
            )
        )
        assert not any("secret-token" in key for key in session._data)

    def test_invalidate_token_swallows_backend_errors(self):
        class ExplodingSession(Session):
            async def _delete(self, key):
                raise RuntimeError("backend down")

        run(ExplodingSession().invalidate_token("tok", "oauth"))

    def test_values_must_be_json_serializable(self, client):
        """Both backends JSON-round-trip, so non-serializable session
        data fails in memory exactly as it would against Redis."""
        session = InMemorySession()
        with pytest.raises(TypeError):
            run(session.store_query("abc", {"bad": object()}, client))


class TestGetSessionFallback:
    def test_redis_url_set_uses_redis(self):
        with patch(
            "courtlistener.mcp.settings.REDIS_URL", "redis://localhost:1"
        ):
            session = get_session()
        assert isinstance(session, RedisSession)

    def test_redis_url_unset_falls_back_to_memory(self):
        with patch("courtlistener.mcp.settings.REDIS_URL", None):
            session = get_session()
        assert isinstance(session, InMemorySession)

    def test_singleton_is_reused(self):
        with patch("courtlistener.mcp.settings.REDIS_URL", None):
            assert get_session() is get_session()

    def test_set_session_overrides(self):
        override = InMemorySession()
        set_session(override)
        assert get_session() is override

    def test_redis_session_builds_client_lazily(self):
        """Constructing the session must not connect; the client is
        created on first use with decoded responses."""
        session = RedisSession("redis://example.test:6379")
        assert session._client is None
        with patch(
            "courtlistener.mcp.session.redis.from_url",
            return_value=MagicMock(),
        ) as from_url:
            _ = session.client
            _ = session.client
        from_url.assert_called_once_with(
            "redis://example.test:6379", decode_responses=True, protocol=3
        )


class TestBaseSessionIsAbstract:
    def test_primitives_raise_not_implemented(self):
        session = Session()
        with pytest.raises(NotImplementedError):
            run(session._get("k"))
        with pytest.raises(NotImplementedError):
            run(session._set("k", "v", 1))
        with pytest.raises(NotImplementedError):
            run(session._delete("k"))
