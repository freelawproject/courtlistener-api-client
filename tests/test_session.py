"""Tests for the Session abstraction: the in-memory backend, the
Redis/in-memory fallback in ``get_session``, and the domain methods
shared by both backends.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError
from redis.exceptions import TimeoutError as RedisTimeoutError

from courtlistener import AsyncCourtListener
from courtlistener.mcp.auth_types import TokenKind
from courtlistener.mcp.session import (
    InMemorySession,
    RedisSession,
    Session,
    active_users_key,
    get_session,
    hmac_hex,
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
    return AsyncCourtListener(api_token="test-token")


def run(coro):
    return asyncio.run(coro)


TODAY = date(2026, 9, 30)


def days_ago(days: int) -> date:
    return TODAY - timedelta(days=days)


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

    @pytest.fixture(autouse=True)
    def stdio_credential(self, monkeypatch):
        monkeypatch.setenv("COURTLISTENER_API_TOKEN", "test-token")

    def test_query_roundtrip(self):
        session = InMemorySession()
        run(session.store_query("abc123", {"response": {"x": 1}}))
        assert run(session.get_query("abc123")) == {"response": {"x": 1}}

    def test_query_missing_returns_none(self):
        session = InMemorySession()
        assert run(session.get_query("nope")) is None

    def test_queries_are_user_scoped(self, monkeypatch):
        session = InMemorySession()
        run(session.store_query("abc123", {"response": 1}))
        monkeypatch.setenv("COURTLISTENER_API_TOKEN", "other-token")
        assert run(session.get_query("abc123")) is None

    def test_user_scoped_key_layout_is_unchanged(self):
        session = InMemorySession()
        run(session.store_query("abc123", {"response": 1}))
        assert list(session._data) == [
            f"mcp:{hmac_hex('test-token')}:query:abc123"
        ]

    def test_citation_analysis_roundtrip(self):
        session = InMemorySession()
        run(session.store_citation_analysis("job1", {"pending": []}))
        assert run(session.get_citation_analysis("job1")) == {"pending": []}

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

    def test_token_kind_interpolates_as_its_bare_value(self):
        """``TokenKind`` members reach the cache key through an f-string,
        so a member and its bare value must build the same key. Python
        3.11 changed mixed-in ``Enum.__format__`` to follow ``__str__``;
        without pinning both to ``str``'s, keys would silently become
        ``mcp:token_info:TokenKind.OAUTH:…`` there and orphan every entry
        written under a different interpreter.
        """
        assert f"{TokenKind.OAUTH}" == "oauth"
        assert str(TokenKind.API) == "api_token"
        assert token_info_key("tok", TokenKind.OAUTH) == token_info_key(
            "tok", "oauth"
        )
        assert ":oauth:" in token_info_key("tok", TokenKind.OAUTH)

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

    def test_values_must_be_json_serializable(self):
        """Both backends JSON-round-trip, so non-serializable session
        data fails in memory exactly as it would against Redis."""
        session = InMemorySession()
        with pytest.raises(TypeError):
            run(session.store_query("abc", {"bad": object()}))


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


class TestRedisSessionDegradation:
    """Connection-level Redis failures (the DNS blips behind Sentry
    MCP-2G) must read as cache misses and skip writes rather than fail
    the request that touched them. Command-level errors still raise:
    those are bugs, and swallowing them would hide corruption."""

    def _failing_session(self, exc: Exception) -> RedisSession:
        session = RedisSession("redis://example.test:6379")
        session._client = MagicMock(
            get=AsyncMock(side_effect=exc),
            set=AsyncMock(side_effect=exc),
            delete=AsyncMock(side_effect=exc),
        )
        return session

    @pytest.mark.parametrize(
        "exc",
        [
            RedisConnectionError(
                "Error -3 connecting to redis:6379. "
                "Temporary failure in name resolution."
            ),
            RedisTimeoutError("Timeout connecting to server"),
        ],
    )
    def test_primitives_degrade_instead_of_raising(self, exc):
        session = self._failing_session(exc)
        assert run(session._get("key")) is None
        run(session._set("key", "value", 60))
        run(session._delete("key"))

    def test_domain_methods_degrade_end_to_end(self, monkeypatch):
        """A blip mid-tool-call surfaces as "not found" (each reader
        already turns ``None`` into a clean retry message) instead of
        an unhandled error."""
        monkeypatch.setenv("COURTLISTENER_API_TOKEN", "test-token")
        session = self._failing_session(RedisConnectionError("dns"))
        assert run(session.get_query("abc")) is None
        run(session.store_query("abc", {"response": 1}))
        assert run(session.get_document("opinion", 42)) is None
        assert run(session.get_token_info("tok", "oauth")) is None

    def test_command_errors_still_raise(self):
        session = self._failing_session(
            ResponseError("WRONGTYPE Operation against a key")
        )
        with pytest.raises(ResponseError):
            run(session._get("key"))


class TestBaseSessionIsAbstract:
    def test_primitives_raise_not_implemented(self):
        session = Session()
        with pytest.raises(NotImplementedError):
            run(session._get("k"))
        with pytest.raises(NotImplementedError):
            run(session._set("k", "v", 1))
        with pytest.raises(NotImplementedError):
            run(session._delete("k"))
        with pytest.raises(NotImplementedError):
            run(session.mark_active("u", "oauth", TODAY))
        with pytest.raises(NotImplementedError):
            run(session.active_users("oauth", 7, TODAY))


class TestRedisSessionPing:
    def _session(self, **ping_kwargs) -> RedisSession:
        session = RedisSession("redis://example.test:6379")
        session._client = MagicMock(ping=AsyncMock(**ping_kwargs))
        return session

    def test_reports_a_reachable_server(self):
        assert run(self._session(return_value=True).ping()) is True

    def test_connection_failure_reads_as_unhealthy(self):
        session = self._session(side_effect=RedisConnectionError("dns"))
        assert run(session.ping()) is False


class TestActiveUsers:
    """Daily active users: one set per credential kind and UTC day,
    counted by unioning the days of the requested window."""

    def test_missing_days_count_as_empty(self):
        session = InMemorySession()
        assert run(session.active_users("oauth", 30, TODAY)) == 0

    def test_counts_distinct_users_across_the_window(self):
        session = InMemorySession()
        run(session.mark_active("u1", "oauth", TODAY))
        run(session.mark_active("u1", "oauth", TODAY))
        run(session.mark_active("u1", "oauth", days_ago(1)))
        run(session.mark_active("u2", "oauth", days_ago(6)))
        run(session.mark_active("u3", "oauth", days_ago(7)))
        assert run(session.active_users("oauth", 1, TODAY)) == 1
        assert run(session.active_users("oauth", 7, TODAY)) == 2
        assert run(session.active_users("oauth", 30, TODAY)) == 3

    def test_credentials_are_counted_separately(self):
        session = InMemorySession()
        run(session.mark_active("u1", "oauth", TODAY))
        run(session.mark_active("u1", "api_token", TODAY))
        run(session.mark_active("u2", "api_token", TODAY))
        assert run(session.active_users("oauth", 1, TODAY)) == 1
        assert run(session.active_users("api_token", 1, TODAY)) == 2

    def test_key_layout(self):
        assert (
            active_users_key("oauth", TODAY) == "mcp:active:oauth:2026-09-30"
        )
        assert (
            active_users_key(TokenKind.API, TODAY)
            == "mcp:active:api_token:2026-09-30"
        )
        session = InMemorySession()
        run(session.mark_active("u1", TokenKind.OAUTH, TODAY))
        assert list(session._active) == ["mcp:active:oauth:2026-09-30"]


class TestRedisActiveUsers:
    def _session(self, execute=None, **commands) -> RedisSession:
        session = RedisSession("redis://example.test:6379")
        pipe = MagicMock(execute=execute or AsyncMock(return_value=[1, True]))
        pipeline = MagicMock()
        pipeline.__aenter__.return_value = pipe
        session._client = MagicMock(
            pipeline=MagicMock(return_value=pipeline), **commands
        )
        session._client.pipe = pipe
        return session

    def test_mark_adds_to_the_day_key_and_refreshes_its_ttl(self):
        """One transaction, so a crash can't leave the key without a TTL."""
        session = self._session()
        run(session.mark_active("u1", "oauth", TODAY))
        session._client.pipeline.assert_called_once_with(transaction=True)
        pipe = session._client.pipe
        pipe.pfadd.assert_called_once_with("mcp:active:oauth:2026-09-30", "u1")
        pipe.expire.assert_called_once_with(
            "mcp:active:oauth:2026-09-30", 60 * 86400
        )
        pipe.execute.assert_awaited_once()

    def test_count_unions_the_window_keys(self):
        session = self._session(pfcount=AsyncMock(return_value=5))
        assert run(session.active_users("api_token", 3, TODAY)) == 5
        session._client.pfcount.assert_awaited_once_with(
            "mcp:active:api_token:2026-09-30",
            "mcp:active:api_token:2026-09-29",
            "mcp:active:api_token:2026-09-28",
        )

    def test_connection_errors_degrade(self):
        exc = RedisConnectionError("dns")
        session = self._session(
            execute=AsyncMock(side_effect=exc),
            pfcount=AsyncMock(side_effect=exc),
        )
        run(session.mark_active("u1", "oauth", TODAY))
        assert run(session.active_users("oauth", 7, TODAY)) is None
