"""The OAuth store: how its backend is chosen from the environment, how
its schema gets created, and how its health is probed."""

from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest
from key_value.aio.errors import StoreSetupError
from key_value.aio.stores.memory import MemoryStore
from key_value.aio.stores.postgresql import PostgreSQLStore
from key_value.aio.stores.redis import RedisStore
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper
from key_value.aio.wrappers.passthrough_cache import PassthroughCacheWrapper

import courtlistener.mcp.storage as storage_mod

pytestmark = pytest.mark.asyncio


def _build(**settings):
    overrides = {"POSTGRES_CONFIGURED": False, "REDIS_URL": None, **settings}
    with patch.multiple(storage_mod, **overrides):
        return storage_mod.build_oauth_store()


class TestBuildClientStorage:
    def test_values_are_always_encrypted(self):
        assert isinstance(_build(), FernetEncryptionWrapper)

    def test_postgres_is_primary_and_redis_the_cache(self):
        store = _build(
            POSTGRES_CONFIGURED=True,
            PGHOST="db.example.test",
            PGPORT=5433,
            PGDATABASE="mcp",
            PGUSER="mcp",
            PGPASSWORD="pa%41ss",
            REDIS_URL="redis://cache.example.test",
        )
        inner = store.key_value
        assert isinstance(inner, PassthroughCacheWrapper)
        primary = inner.primary_key_value
        assert isinstance(primary, PostgreSQLStore)
        assert isinstance(inner.unwrapped_cache_key_value, RedisStore)
        assert primary._host == "db.example.test"
        assert primary._port == 5433
        assert primary._database == "mcp"
        assert primary._password == "pa%41ss"

    def test_workers_never_create_the_schema(self):
        store = _build(POSTGRES_CONFIGURED=True)
        assert isinstance(store.key_value, PostgreSQLStore)
        assert store.key_value._auto_create is False

    def test_redis_alone_holds_the_state(self):
        store = _build(REDIS_URL="redis://cache.example.test")
        assert isinstance(store.key_value, RedisStore)

    def test_nothing_configured_falls_back_to_memory(self):
        assert isinstance(_build().key_value, MemoryStore)


def _setup_error(cause):
    """The wrapped error the library raises when a store's setup fails."""
    error = StoreSetupError(message=str(cause), extra_info={})
    error.__cause__ = cause
    return error


def _creating_store(*errors):
    """A stand-in ``PostgreSQLStore`` whose setup fails *errors* times first."""
    store = MagicMock()
    store.__aenter__ = AsyncMock(
        side_effect=[*map(_setup_error, errors), store]
    )
    store.__aexit__ = AsyncMock(return_value=False)
    return store


class TestInitSchema:
    async def test_lets_the_store_create_its_own_table(self):
        store = _creating_store()
        with patch.object(
            storage_mod, "PostgreSQLStore", return_value=store
        ) as cls:
            await storage_mod.postgres_init_schema()
        assert cls.call_args.kwargs["auto_create"] is True
        store.__aenter__.assert_awaited_once()

    async def test_retries_when_another_pod_created_it_first(self):
        store = _creating_store(
            asyncpg.exceptions.UniqueViolationError(
                "pg_type_typname_nsp_index"
            )
        )
        with (
            patch.object(storage_mod, "PostgreSQLStore", return_value=store),
            patch.object(storage_mod.asyncio, "sleep", new=AsyncMock()),
        ):
            await storage_mod.postgres_init_schema()
        assert store.__aenter__.await_count == 2

    async def test_gives_up_after_the_last_attempt(self):
        errors = [asyncpg.exceptions.DuplicateTableError("kv_store")] * 2
        store = _creating_store(*errors)
        with (
            patch.object(storage_mod, "PostgreSQLStore", return_value=store),
            patch.object(storage_mod.asyncio, "sleep", new=AsyncMock()),
            pytest.raises(StoreSetupError),
        ):
            await storage_mod.postgres_init_schema(attempts=2)

    async def test_retries_while_postgres_is_unreachable(self):
        store = _creating_store(
            OSError("refused"),
            asyncpg.exceptions.CannotConnectNowError("starting up"),
        )
        with (
            patch.object(storage_mod, "PostgreSQLStore", return_value=store),
            patch.object(storage_mod.asyncio, "sleep", new=AsyncMock()),
        ):
            await storage_mod.postgres_init_schema()
        assert store.__aenter__.await_count == 3

    async def test_other_errors_are_not_retried(self):
        store = _creating_store(
            asyncpg.exceptions.InsufficientPrivilegeError("denied")
        )
        with (
            patch.object(storage_mod, "PostgreSQLStore", return_value=store),
            pytest.raises(StoreSetupError),
        ):
            await storage_mod.postgres_init_schema()
        store.__aenter__.assert_awaited_once()


class TestStoreReady:
    @pytest.fixture(autouse=True)
    def fresh_storage(self):
        storage_mod.set_oauth_store(None)
        yield
        storage_mod.set_oauth_store(None)

    async def test_a_readable_store_is_ready(self):
        storage_mod.set_oauth_store(
            MagicMock(get=AsyncMock(return_value=None))
        )
        assert await storage_mod.oauth_store_ready() is True

    async def test_a_missing_table_is_not_ready(self):
        storage_mod.set_oauth_store(
            MagicMock(get=AsyncMock(side_effect=ValueError("no table")))
        )
        assert await storage_mod.oauth_store_ready() is False

    async def test_the_store_is_built_once(self):
        with patch.object(
            storage_mod, "build_oauth_store", return_value=MemoryStore()
        ) as build:
            first = storage_mod.get_oauth_store()
            assert storage_mod.get_oauth_store() is first
        build.assert_called_once()

    async def test_connect_passes_the_settings_explicitly(self):
        with (
            patch.multiple(
                storage_mod,
                PGHOST="db.example.test",
                PGPORT=5433,
                PGUSER="mcp",
                PGPASSWORD="pa%41ss",
                PGDATABASE="mcp",
            ),
            patch.object(
                storage_mod.asyncpg, "connect", new=AsyncMock()
            ) as connect,
        ):
            await storage_mod.postgres_connect(timeout=5)
        assert connect.await_args.kwargs == {
            "host": "db.example.test",
            "port": 5433,
            "user": "mcp",
            "password": "pa%41ss",
            "database": "mcp",
            "timeout": 5,
        }
