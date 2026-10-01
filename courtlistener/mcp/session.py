from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from collections.abc import Awaitable, Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any, cast

import redis.asyncio as redis
from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.dependencies import get_access_token

from courtlistener.mcp import settings
from courtlistener.mcp.auth_types import TokenInfo, TokenKind
from courtlistener.mcp.settings import (
    ACTIVE_USERS_TTL_SECONDS,
    DOCUMENT_TTL_SECONDS,
    MCP_SECRET_BYTES,
    SESSION_TTL_SECONDS,
    TOKEN_CACHE_TTL_SECONDS,
)
from courtlistener.settings import get_api_token

logger = logging.getLogger(__name__)


def json_default(obj):
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def hmac_hex(value: str) -> str:
    return hmac.new(
        MCP_SECRET_BYTES, value.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def token_info_key(token: str, kind: TokenKind) -> str:
    """Cache key for a verified credential."""
    return f"mcp:token_info:{kind}:{hmac_hex(token)}"


def active_users_key(credential: str, day: date) -> str:
    """Key of the set of users active on *day* under *credential*."""
    return f"mcp:active:{credential}:{day.isoformat()}"


def active_users_keys(credential: str, days: int, today: date) -> list[str]:
    """Keys of the *days* days ending on *today*, newest first."""
    return [
        active_users_key(credential, today - timedelta(days=offset))
        for offset in range(days)
    ]


def utc_today() -> date:
    """The current UTC date, which activity is bucketed by."""
    return datetime.now(timezone.utc).date()


def token_user_key(access_token: AccessToken) -> str:
    """A verified token's ``user_hash`` claim, else an HMAC of the token."""
    return access_token.claims.get("user_hash") or hmac_hex(access_token.token)


def user_key() -> str:
    """The per-user key prefix for the current request.

    HTTP mode: see ``token_user_key``. stdio mode: an HMAC of the env var
    credential.
    """
    access_token = get_access_token()
    if access_token is not None:
        return token_user_key(access_token)
    token = get_api_token()
    if not token:
        raise ValueError("No credential; cannot derive the user key.")
    return hmac_hex(token)


class Session:
    """Storage backend for MCP server state."""

    async def _get(self, key: str) -> str | None:
        raise NotImplementedError("_get must be implemented by subclass")

    async def _set(self, key: str, value: str, ttl_seconds: int) -> None:
        raise NotImplementedError("_set must be implemented by subclass")

    async def _delete(self, key: str) -> None:
        raise NotImplementedError("_delete must be implemented by subclass")

    async def _get_user_scoped(self, suffix: str) -> Any:
        raw = await self._get(f"mcp:{user_key()}:{suffix}")
        if raw is None:
            return None
        return json.loads(raw)

    async def _set_user_scoped(self, suffix: str, value: Any) -> None:
        await self._set(
            f"mcp:{user_key()}:{suffix}",
            json.dumps(value, default=json_default),
            SESSION_TTL_SECONDS,
        )

    async def get_query(self, query_id: str) -> dict | None:
        return await self._get_user_scoped(f"query:{query_id}")

    async def store_query(self, query_id: str, data: dict) -> None:
        await self._set_user_scoped(f"query:{query_id}", data)

    async def get_citation_analysis(self, job_id: str) -> dict | None:
        return await self._get_user_scoped(f"citation:{job_id}")

    async def store_citation_analysis(self, job_id: str, data: dict) -> None:
        await self._set_user_scoped(f"citation:{job_id}", data)

    async def get_document(self, doc_type: str, doc_id: int) -> str | None:
        return await self._get(f"mcp:doc:{doc_type}:{doc_id}")

    async def store_document(
        self, doc_type: str, doc_id: int, text: str
    ) -> None:
        # Not user-scoped so that fetched documents are shared across users.
        await self._set(
            f"mcp:doc:{doc_type}:{doc_id}", text, DOCUMENT_TTL_SECONDS
        )

    async def get_token_info(
        self, token: str, kind: TokenKind
    ) -> TokenInfo | None:
        """Return the cached verification of *token* as a *kind* credential."""
        raw = await self._get(token_info_key(token, kind))
        if raw is None:
            return None
        return json.loads(raw)

    async def store_token_info(
        self, token: str, kind: TokenKind, info: TokenInfo
    ) -> None:
        await self._set(
            token_info_key(token, kind),
            json.dumps(info),
            TOKEN_CACHE_TTL_SECONDS,
        )

    async def invalidate_token(self, token: str, kind: TokenKind) -> None:
        """Drop a cached token verification."""
        try:
            await self._delete(token_info_key(token, kind))
        except Exception as exc:
            logger.warning("failed to invalidate token cache: %s", exc)

    async def mark_active(
        self, user_hash: str, credential: str, day: date
    ) -> bool:
        """Record *user_hash* as active on *day*; ``False`` if not stored."""
        raise NotImplementedError(
            "mark_active must be implemented by subclass"
        )

    async def active_users(
        self, credential: str, days: int, today: date
    ) -> int | None:
        """Distinct users active in the *days* days ending on *today*.

        ``None`` when the store is unavailable.
        """
        raise NotImplementedError(
            "active_users must be implemented by subclass"
        )


@contextmanager
def degrade_on_connection_error(op: str) -> Iterator[None]:
    """Treat redis connection errors as cache misses."""
    try:
        yield
    except (redis.ConnectionError, redis.TimeoutError) as exc:
        logger.error("redis %s failed; degrading to miss: %s", op, exc)


class RedisSession(Session):
    """Redis-backed session storage, shared across workers."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._client: redis.Redis | None = None

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.from_url(
                self._url, decode_responses=True, protocol=3
            )
        return self._client

    async def _get(self, key: str) -> str | None:
        with degrade_on_connection_error("get"):
            return await self.client.get(key)
        return None

    async def _set(self, key: str, value: str, ttl_seconds: int) -> None:
        with degrade_on_connection_error("set"):
            await self.client.set(key, value, ex=ttl_seconds)

    async def _delete(self, key: str) -> None:
        with degrade_on_connection_error("delete"):
            await self.client.delete(key)

    async def mark_active(
        self, user_hash: str, credential: str, day: date
    ) -> bool:
        key = active_users_key(credential, day)
        with degrade_on_connection_error("pfadd"):
            async with self.client.pipeline(transaction=True) as pipe:
                pipe.pfadd(key, user_hash)
                pipe.expire(key, ACTIVE_USERS_TTL_SECONDS)
                await pipe.execute()
            return True
        return False

    async def active_users(
        self, credential: str, days: int, today: date
    ) -> int | None:
        keys = active_users_keys(credential, days, today)
        with degrade_on_connection_error("pfcount"):
            return int(await self.client.pfcount(*keys))
        return None

    async def ping(self) -> bool:
        with degrade_on_connection_error("ping"):
            return bool(await cast("Awaitable[bool]", self.client.ping()))
        return False


class InMemorySession(Session):
    """Dict-backed session storage for local/stdio use without Redis."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float]] = {}
        self._active: dict[str, set[str]] = {}

    async def _get(self, key: str) -> str | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() >= expires_at:
            del self._data[key]
            return None
        return value

    async def _set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._data[key] = (value, time.monotonic() + ttl_seconds)

    async def _delete(self, key: str) -> None:
        self._data.pop(key, None)

    async def mark_active(
        self, user_hash: str, credential: str, day: date
    ) -> bool:
        key = active_users_key(credential, day)
        self._active.setdefault(key, set()).add(user_hash)
        return True

    async def active_users(
        self, credential: str, days: int, today: date
    ) -> int:
        active: set[str] = set()
        for key in active_users_keys(credential, days, today):
            active |= self._active.get(key, set())
        return len(active)


_session: Session | None = None


def get_session() -> Session:
    """Return the process-wide session store, creating it on first use."""
    global _session
    if _session is None:
        url = settings.REDIS_URL
        if url:
            _session = RedisSession(url)
        else:
            logger.warning(
                "REDIS_URL is not set; using in-memory sessions. State "
                "is per-process and will be lost on restart."
            )
            _session = InMemorySession()
    return _session


def set_session(session: Session | None) -> None:
    """Replace the process-wide session store (for tests)."""
    global _session
    _session = session
