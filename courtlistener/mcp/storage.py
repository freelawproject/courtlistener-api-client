import argparse
import asyncio
import logging
from typing import Any

import asyncpg
from cryptography.fernet import Fernet
from key_value.aio.errors import StoreSetupError
from key_value.aio.protocols import AsyncKeyValue
from key_value.aio.stores.memory import MemoryStore
from key_value.aio.stores.postgresql import PostgreSQLStore
from key_value.aio.stores.redis import RedisStore
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper
from key_value.aio.wrappers.passthrough_cache import PassthroughCacheWrapper

from courtlistener.mcp.settings import (
    MCP_STORAGE_ENCRYPTION_KEY,
    PGDATABASE,
    PGHOST,
    PGPASSWORD,
    PGPOOL_MAX,
    PGPORT,
    PGUSER,
    POSTGRES_CONFIGURED,
    REDIS_URL,
)

logger = logging.getLogger(__name__)

SCHEMA_RACE_ERRORS = (
    asyncpg.exceptions.UniqueViolationError,
    asyncpg.exceptions.DuplicateTableError,
    asyncpg.exceptions.DuplicateObjectError,
)
TRANSIENT_ERRORS = (
    OSError,
    TimeoutError,
    asyncpg.exceptions.PostgresConnectionError,
    asyncpg.exceptions.CannotConnectNowError,
)
RETRYABLE_ERRORS = SCHEMA_RACE_ERRORS + TRANSIENT_ERRORS


def postgres_connect(**kwargs: Any) -> Any:
    """Open an asyncpg connection to the OAuth store database."""
    return asyncpg.connect(
        host=PGHOST,
        port=PGPORT,
        user=PGUSER,
        password=PGPASSWORD,
        database=PGDATABASE,
        **kwargs,
    )


class PostgresStore(PostgreSQLStore):
    """``PostgreSQLStore`` with a small connection pool; the library's
    default holds ten connections per worker process."""

    async def _create_pool(self) -> Any:
        return await asyncpg.create_pool(
            host=PGHOST,
            port=PGPORT,
            database=PGDATABASE,
            user=PGUSER,
            password=PGPASSWORD,
            min_size=1,
            max_size=PGPOOL_MAX,
        )


def postgres_store(*, auto_create: bool) -> PostgresStore:
    """The Postgres tier of the OAuth store."""
    return PostgresStore(
        host=PGHOST,
        port=PGPORT,
        database=PGDATABASE,
        user=PGUSER,
        password=PGPASSWORD,
        auto_create=auto_create,
    )


async def postgres_init_schema(attempts: int = 10) -> None:
    """Have the store create its own table, retrying past concurrent runs and
    a Postgres that is still coming up."""
    for attempt in range(1, attempts + 1):
        try:
            async with postgres_store(auto_create=True):
                return
        except StoreSetupError as exc:
            if attempt == attempts or not isinstance(
                exc.__cause__, RETRYABLE_ERRORS
            ):
                raise
            logger.info("schema creation failed (%r); retrying", exc.__cause__)
            await asyncio.sleep(0.5 * attempt)


def build_oauth_store() -> AsyncKeyValue:
    """The OAuth server's state store: encrypted rows in Postgres, read through Redis."""
    store: AsyncKeyValue
    if POSTGRES_CONFIGURED:
        store = postgres_store(auto_create=False)
        if REDIS_URL:
            store = PassthroughCacheWrapper(store, RedisStore(url=REDIS_URL))
    elif REDIS_URL:
        logger.warning(
            "PGHOST is not set; OAuth clients and tokens live only in Redis."
        )
        store = RedisStore(url=REDIS_URL)
    else:
        logger.warning(
            "Neither PGHOST nor REDIS_URL is set; OAuth state is in memory."
        )
        store = MemoryStore()
    return FernetEncryptionWrapper(
        store,
        fernet=Fernet(MCP_STORAGE_ENCRYPTION_KEY),
        raise_on_decryption_error=False,
    )


_oauth_store: AsyncKeyValue | None = None


def get_oauth_store() -> AsyncKeyValue:
    """The process-wide OAuth state store, built on first use."""
    global _oauth_store
    if _oauth_store is None:
        _oauth_store = build_oauth_store()
    return _oauth_store


def set_oauth_store(storage: AsyncKeyValue | None) -> None:
    """Replace the process-wide OAuth state store (for tests)."""
    global _oauth_store
    _oauth_store = storage


async def oauth_store_ready() -> bool:
    """Whether the OAuth store answers reads, which needs its table to exist."""
    try:
        await get_oauth_store().get(key="probe", collection="health")
    except Exception as exc:
        logger.warning("OAuth store probe failed: %s", exc)
        return False
    return True


def main() -> None:
    """``init`` creates the store's schema if it is missing."""
    parser = argparse.ArgumentParser(description="Maintain the OAuth store.")
    parser.add_argument("command", choices=["init"])
    parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(postgres_init_schema())
    logger.info("OAuth store schema ready")


if __name__ == "__main__":
    main()
