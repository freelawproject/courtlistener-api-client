import logging
import os

from cryptography.fernet import Fernet
from key_value.aio.protocols import AsyncKeyValue
from key_value.aio.stores.memory import MemoryStore
from key_value.aio.stores.postgresql import PostgreSQLStore
from key_value.aio.stores.redis import RedisStore
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper
from key_value.aio.wrappers.passthrough_cache import PassthroughCacheWrapper

from courtlistener.mcp.settings import (
    MCP_STORAGE_ENCRYPTION_KEY,
    POSTGRES_CONFIGURED,
    REDIS_URL,
)

logger = logging.getLogger(__name__)


def build_client_storage() -> AsyncKeyValue:
    """The OAuth server's store: encrypted rows in Postgres, read through Redis."""
    store: AsyncKeyValue
    if POSTGRES_CONFIGURED:
        store = PostgreSQLStore(
            host=os.environ["PGHOST"],
            port=int(os.getenv("PGPORT") or 5432),
            database=os.getenv("PGDATABASE") or "postgres",
            user=os.getenv("PGUSER"),
            password=os.getenv("PGPASSWORD"),
        )
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
