from __future__ import annotations

import hashlib
import json
import uuid
from abc import ABC, abstractmethod
from copy import deepcopy
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis import Redis


class SessionStore(ABC):
    """Abstraction over session state storage."""

    def make_id(self) -> str:
        """Generate a short UUID for a new query/job."""
        return uuid.uuid4().hex[:8]

    @abstractmethod
    def store_query(self, user_id: str, query_id: str, data: dict) -> None: ...

    @abstractmethod
    def get_query(self, user_id: str, query_id: str) -> dict | None: ...

    @abstractmethod
    def store_citation_analysis(
        self, user_id: str, job_id: str, data: dict
    ) -> None: ...

    @abstractmethod
    def get_citation_analysis(
        self, user_id: str, job_id: str
    ) -> dict | None: ...

    @staticmethod
    def hash_token(token: str) -> str:
        """Derive a user identifier from an API token.

        Returns a 16-char hex string (truncated SHA-256). Never store
        the raw token — only this hash is used as a Redis key prefix.
        """
        return hashlib.sha256(token.encode()).hexdigest()[:16]


class InMemorySessionStore(SessionStore):
    """Dict-backed store for stdio mode (single user, single process).

    Not thread-safe — suitable for single-process stdio servers only.
    """

    def __init__(self) -> None:
        self._data: dict[str, dict] = {}

    def store_query(self, user_id: str, query_id: str, data: dict) -> None:
        self._data[f"{user_id}:query:{query_id}"] = deepcopy(data)

    def get_query(self, user_id: str, query_id: str) -> dict | None:
        return self._data.get(f"{user_id}:query:{query_id}")

    def store_citation_analysis(
        self, user_id: str, job_id: str, data: dict
    ) -> None:
        self._data[f"{user_id}:citation:{job_id}"] = data

    def get_citation_analysis(self, user_id: str, job_id: str) -> dict | None:
        return self._data.get(f"{user_id}:citation:{job_id}")


class RedisSessionStore(SessionStore):
    """Redis-backed store for HTTP mode (multi-tenant, persistent).

    Requires ``redis>=5.0.0`` (installed via the ``[mcp]`` extra).
    Keys follow the format ``mcp:{user_id}:{type}:{id}`` where
    ``user_id`` should be a hashed token (see :meth:`hash_token`).
    """

    QUERY_TTL = 3600  # 1 hour
    CITATION_TTL = 7200  # 2 hours

    def __init__(self, redis_client: Redis) -> None:
        self._redis = redis_client

    def store_query(self, user_id: str, query_id: str, data: dict) -> None:
        key = f"mcp:{user_id}:query:{query_id}"
        self._redis.set(key, json.dumps(data), ex=self.QUERY_TTL)

    def get_query(self, user_id: str, query_id: str) -> dict | None:
        key = f"mcp:{user_id}:query:{query_id}"
        raw = self._redis.get(key)
        return json.loads(raw) if raw else None

    def store_citation_analysis(
        self, user_id: str, job_id: str, data: dict
    ) -> None:
        key = f"mcp:{user_id}:citation:{job_id}"
        self._redis.set(key, json.dumps(data), ex=self.CITATION_TTL)

    def get_citation_analysis(self, user_id: str, job_id: str) -> dict | None:
        key = f"mcp:{user_id}:citation:{job_id}"
        raw = self._redis.get(key)
        return json.loads(raw) if raw else None
