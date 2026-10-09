"""``build_client_storage`` picks the OAuth state backend from the
environment: encrypted rows in Postgres read through Redis in production,
with Redis-only and in-memory fallbacks for smaller setups and tests."""

from unittest.mock import patch

from key_value.aio.stores.memory import MemoryStore
from key_value.aio.stores.postgresql import PostgreSQLStore
from key_value.aio.stores.redis import RedisStore
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper
from key_value.aio.wrappers.passthrough_cache import PassthroughCacheWrapper

import courtlistener.mcp.storage as storage_mod


def _build(**settings):
    overrides = {"POSTGRES_CONFIGURED": False, "REDIS_URL": None, **settings}
    with patch.multiple(storage_mod, **overrides):
        return storage_mod.build_client_storage()


class TestBuildClientStorage:
    def test_values_are_always_encrypted(self):
        assert isinstance(_build(), FernetEncryptionWrapper)

    def test_postgres_is_primary_and_redis_the_cache(self, monkeypatch):
        monkeypatch.setenv("PGHOST", "db.example.test")
        monkeypatch.setenv("PGPORT", "5433")
        monkeypatch.setenv("PGDATABASE", "mcp")
        monkeypatch.setenv("PGUSER", "mcp")
        monkeypatch.setenv("PGPASSWORD", "pa%41ss")
        store = _build(
            POSTGRES_CONFIGURED=True, REDIS_URL="redis://cache.example.test"
        )
        inner = store.key_value
        assert isinstance(inner, PassthroughCacheWrapper)
        assert isinstance(inner.primary_key_value, PostgreSQLStore)
        assert isinstance(inner.unwrapped_cache_key_value, RedisStore)
        assert inner.primary_key_value._host == "db.example.test"
        assert inner.primary_key_value._port == 5433
        assert inner.primary_key_value._database == "mcp"
        assert inner.primary_key_value._password == "pa%41ss"

    def test_postgres_without_redis_has_no_cache_tier(self, monkeypatch):
        monkeypatch.setenv("PGHOST", "db.example.test")
        store = _build(POSTGRES_CONFIGURED=True)
        assert isinstance(store.key_value, PostgreSQLStore)

    def test_redis_alone_holds_the_state(self):
        store = _build(REDIS_URL="redis://cache.example.test")
        assert isinstance(store.key_value, RedisStore)

    def test_nothing_configured_falls_back_to_memory(self):
        assert isinstance(_build().key_value, MemoryStore)
