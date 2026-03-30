"""Tests for the SessionStore abstraction."""

import json
from unittest.mock import MagicMock

from courtlistener.mcp.session import (
    InMemorySessionStore,
    RedisSessionStore,
    SessionStore,
)


class TestMakeId:
    """Tests for SessionStore.make_id()."""

    def test_returns_8_char_hex_string(self):
        store = InMemorySessionStore()
        id_ = store.make_id()
        assert len(id_) == 8
        assert all(c in "0123456789abcdef" for c in id_)

    def test_returns_unique_values(self):
        store = InMemorySessionStore()
        ids = {store.make_id() for _ in range(100)}
        assert len(ids) == 100


class TestHashToken:
    """Tests for SessionStore.hash_token()."""

    def test_returns_16_char_hex(self):
        h = SessionStore.hash_token("test-token-123")
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)

    def test_deterministic(self):
        a = SessionStore.hash_token("same-token")
        b = SessionStore.hash_token("same-token")
        assert a == b

    def test_different_tokens_different_hashes(self):
        a = SessionStore.hash_token("token-a")
        b = SessionStore.hash_token("token-b")
        assert a != b


class TestInMemorySessionStore:
    """Tests for InMemorySessionStore."""

    def setup_method(self):
        self.store = InMemorySessionStore()

    # --- Query tests ---

    def test_store_and_get_query(self):
        data = {"response": "serialized", "fields": ["name"]}
        self.store.store_query("user1", "abc12345", data)
        assert self.store.get_query("user1", "abc12345") == data

    def test_get_nonexistent_query_returns_none(self):
        assert self.store.get_query("user1", "nope") is None

    def test_query_user_isolation(self):
        """User A cannot see user B's queries."""
        self.store.store_query("userA", "q1", {"a": 1})
        self.store.store_query("userB", "q1", {"b": 2})
        assert self.store.get_query("userA", "q1") == {"a": 1}
        assert self.store.get_query("userB", "q1") == {"b": 2}
        assert self.store.get_query("userA", "q2") is None

    def test_overwrite_query(self):
        """Subsequent store_query calls overwrite previous data."""
        self.store.store_query("user1", "q1", {"v": 1})
        self.store.store_query("user1", "q1", {"v": 2})
        assert self.store.get_query("user1", "q1") == {"v": 2}

    # --- Citation analysis tests ---

    def test_store_and_get_citation_analysis(self):
        data = {"pending": [], "verified": {}}
        self.store.store_citation_analysis("user1", "job1", data)
        result = self.store.get_citation_analysis("user1", "job1")
        assert result == data

    def test_get_nonexistent_citation_returns_none(self):
        result = self.store.get_citation_analysis("user1", "nope")
        assert result is None

    def test_citation_user_isolation(self):
        """User A cannot see user B's citation analyses."""
        self.store.store_citation_analysis("userA", "j1", {"a": 1})
        self.store.store_citation_analysis("userB", "j1", {"b": 2})
        assert self.store.get_citation_analysis("userA", "j1") == {
            "a": 1
        }
        assert self.store.get_citation_analysis("userB", "j1") == {
            "b": 2
        }

    def test_overwrite_citation_analysis(self):
        """Subsequent store_citation_analysis calls overwrite previous data."""
        self.store.store_citation_analysis(
            "user1", "j1", {"pending": [1]}
        )
        self.store.store_citation_analysis(
            "user1", "j1", {"pending": []}
        )
        assert self.store.get_citation_analysis("user1", "j1") == {
            "pending": []
        }


class TestRedisSessionStore:
    """Tests for RedisSessionStore using a mocked Redis client."""

    def setup_method(self):
        self.mock_redis = MagicMock()
        self.store = RedisSessionStore(self.mock_redis)

    # --- Query tests ---

    def test_store_query_calls_redis_set_with_ttl(self):
        data = {"response": "test"}
        self.store.store_query("uid", "q1", data)
        self.mock_redis.set.assert_called_once_with(
            "mcp:uid:query:q1",
            json.dumps(data),
            ex=3600,
        )

    def test_get_query_returns_parsed_json(self):
        data = {"response": "test"}
        self.mock_redis.get.return_value = json.dumps(data)
        result = self.store.get_query("uid", "q1")
        self.mock_redis.get.assert_called_once_with(
            "mcp:uid:query:q1"
        )
        assert result == data

    def test_get_query_returns_none_when_missing(self):
        self.mock_redis.get.return_value = None
        assert self.store.get_query("uid", "q1") is None

    # --- Citation analysis tests ---

    def test_store_citation_calls_redis_set_with_ttl(self):
        data = {"pending": []}
        self.store.store_citation_analysis("uid", "j1", data)
        self.mock_redis.set.assert_called_once_with(
            "mcp:uid:citation:j1",
            json.dumps(data),
            ex=7200,
        )

    def test_get_citation_returns_parsed_json(self):
        data = {"pending": []}
        self.mock_redis.get.return_value = json.dumps(data)
        result = self.store.get_citation_analysis("uid", "j1")
        self.mock_redis.get.assert_called_once_with(
            "mcp:uid:citation:j1"
        )
        assert result == data

    def test_get_citation_returns_none_when_missing(self):
        self.mock_redis.get.return_value = None
        result = self.store.get_citation_analysis("uid", "nope")
        assert result is None

    # --- Key format tests ---

    def test_query_key_format(self):
        self.store.store_query("abc123", "def456", {})
        key = self.mock_redis.set.call_args[0][0]
        assert key == "mcp:abc123:query:def456"

    def test_citation_key_format(self):
        self.store.store_citation_analysis("abc123", "def456", {})
        key = self.mock_redis.set.call_args[0][0]
        assert key == "mcp:abc123:citation:def456"

    # --- TTL constant tests ---

    def test_query_ttl_is_one_hour(self):
        assert RedisSessionStore.QUERY_TTL == 3600

    def test_citation_ttl_is_two_hours(self):
        assert RedisSessionStore.CITATION_TTL == 7200
