import hashlib
import hmac
import json
import logging
import os
import uuid
from datetime import date, datetime
from itertools import islice
from typing import Any

import httpx
import redis.asyncio as redis
import tiktoken
from fastmcp.server.dependencies import get_access_token

from courtlistener import CourtListener
from courtlistener.resource import ResourceIterator

logger = logging.getLogger(__name__)

DEFAULT_NUM_RESULTS = 20
MAX_NUM_RESULTS = 100

# Session-scoped keys live in Redis for this long before being evicted.
SESSION_TTL_SECONDS = 3600

# How long a token→user_hash mapping is cached.
TOKEN_CACHE_TTL_SECONDS = int(os.getenv("MCP_TOKEN_CACHE_TTL", "600"))

REDIS_URL = os.getenv("REDIS_URL")

GIT_SHA = os.getenv("GIT_SHA", "unknown")

MCP_BASE_URL = os.getenv("MCP_BASE_URL", "https://mcp.courtlistener.com")

OAUTH_ISSUER = os.getenv(
    "COURTLISTENER_OAUTH_ISSUER", "https://www.courtlistener.com"
)

OAUTH_USERINFO_URL = os.getenv(
    "COURTLISTENER_OAUTH_USERINFO_URL",
    f"{OAUTH_ISSUER.rstrip('/')}/o/userinfo/",
)

MCP_SECRET_KEY = os.getenv("MCP_SECRET_KEY")
if not MCP_SECRET_KEY:
    MCP_SECRET_KEY = "insecure-do-not-use-in-production"
    logger.warning(
        "MCP_SECRET_KEY is not set; falling back to an insecure default. "
        "Set a strong random value before going to production."
    )
MCP_SECRET_BYTES = MCP_SECRET_KEY.encode("utf-8")

redis_client: redis.Redis | None = None


def json_default(obj):
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def collect_results(
    response: ResourceIterator, num_results: int = DEFAULT_NUM_RESULTS
) -> list[dict]:
    """Consume up to *num_results* items from a ResourceIterator.

    Uses the iterator protocol so ``_page_result_index`` is kept in sync,
    which means a subsequent ``dump()`` will capture the correct resume
    point.
    """
    return list(islice(response, num_results))


async def prepare_query_id(
    response: ResourceIterator,
    client: CourtListener,
    fields: list[str] | None = None,
) -> str:
    """Store query response in Redis and return a short UUID query ID."""
    query_id = make_id()
    data: dict = {"response": response.dump()}
    if fields is not None:
        data["fields"] = fields
    await store_session_query(query_id, data, client)
    return query_id


def filter_results_by_fields(
    results: list[dict], fields: list[str] | None
) -> tuple[list[dict], bool]:
    """Apply client-side field filtering to a list of result dicts.

    Returns the (possibly filtered) results and a boolean indicating
    whether any requested fields were missing from the data.
    """
    if not fields:
        return results, False
    missing = any(k not in result for result in results for k in fields)
    filtered = [{k: v for k, v in r.items() if k in fields} for r in results]
    return filtered, missing


def prepare_choices_str(
    choices,
    endpoint_id: str = "",
    field_name: str = "",
    max_tokens=1000,
    snippet_count=5,
):
    if not choices:
        return ""

    choices_str = json.dumps(choices, indent=2)
    num_tokens = len(tiktoken.get_encoding("cl100k_base").encode(choices_str))
    if num_tokens > max_tokens:
        snippet = ", ".join(
            f"{c['value']} ({c['display_name']})"
            for c in choices[:snippet_count]
        )
        return (
            f"This field has {len(choices)} valid choices. "
            f"Examples: {snippet}, ...\n\n"
            f"Use the `get_choices` tool with "
            f'endpoint_id="{endpoint_id}" and '
            f'field_name="{field_name}" to see all choices.'
        )

    choices_str = "Valid choices:\n\n" + choices_str
    return choices_str


def prepare_filter(filter, endpoint_id: str = "", field_name: str = ""):
    choices_str = prepare_choices_str(
        filter.get("choices"),
        endpoint_id=endpoint_id,
        field_name=field_name,
    )
    filter["description"] = (
        filter.get("description", "") + "\n\n" + choices_str
    ).strip()
    for key in ["choices", "title", "related_class_name", "default"]:
        if key in filter:
            del filter[key]
    return filter


def prepare_count(count: int | str | None, query_id: str) -> int | str | None:
    if isinstance(count, int):
        return count
    elif isinstance(count, str):
        return (
            f"To get the count use the `get_counts` tool with "
            f'query_id="{query_id}".'
        )
    return None


def has_more_results(response: ResourceIterator) -> bool:
    """Check whether a ResourceIterator has unconsumed results."""
    page = response.current_page
    if response._page_result_index < len(page.results):
        return True
    return response.has_next()


def prepare_has_more_str(
    response: ResourceIterator, query_id: str
) -> str | None:
    if has_more_results(response):
        return (
            f"More results are available. Use the `get_more_results` "
            f'tool with query_id="{query_id}" to retrieve them.'
        )
    return None


# User-scoped Redis session helpers.
#
# Keyed by an HMAC of the caller's API token rather than the MCP session id,
# so state survives across stateless_http=True requests and across workers.
def get_redis() -> redis.Redis:
    """Lazily build a module-level async Redis client from REDIS_URL."""
    global redis_client
    if redis_client is None:
        url = os.environ.get("REDIS_URL")
        if not url:
            raise RuntimeError(
                "REDIS_URL is not set; cannot access session store."
            )
        redis_client = redis.from_url(url, decode_responses=True)
    return redis_client


def hmac_hex(value: str) -> str:
    return hmac.new(
        MCP_SECRET_BYTES, value.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def token_cache_key(token: str) -> str:
    """Redis key for the token→user_hash mapping set by the verifier."""
    return f"mcp:token_to_user:{hmac_hex(token)}"


async def resolve_user_hash_via_userinfo(token: str) -> str | None:
    """Return the stable user_hash for *token*, hitting userinfo on cache miss.

    Called from the auth verifier (see ``UserInfoTokenVerifier``). Returns
    ``None`` if CL rejects the token, which the verifier translates into a
    proper HTTP 401 at the auth layer.

    The cache key is ``HMAC(token)``; the cache value is ``HMAC(sub)``. The
    token never lands in Redis in plaintext, and the namespace is derived
    from the stable OIDC ``sub`` claim so that rotated tokens still map to
    the same user.
    """
    r = get_redis()
    cache_key = token_cache_key(token)
    cached = await r.get(cache_key)
    if cached:
        return cached

    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.get(
                OAUTH_USERINFO_URL,
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError as exc:
        logger.warning("userinfo call failed: %s", exc)
        return None

    if resp.status_code != 200:
        # 401 from userinfo == revoked/expired/invalid. Don't cache.
        return None

    sub = resp.json().get("sub")
    if not sub:
        logger.warning("userinfo response missing `sub` claim")
        return None

    uh = hmac_hex(str(sub))
    await r.set(cache_key, uh, ex=TOKEN_CACHE_TTL_SECONDS)
    return uh


async def invalidate_token_cache(token: str) -> None:
    """Drop a token→user_hash mapping.

    Called when CL rejects a token mid-cache (e.g. 401 on a downstream
    API call). The *next* MCP request for this token will miss the cache,
    re-hit userinfo, fail, and cause a proper HTTP 401 from the auth layer
    so the MCP client re-runs OAuth.
    """
    try:
        await get_redis().delete(token_cache_key(token))
    except Exception as exc:
        logger.warning("failed to invalidate token cache: %s", exc)


def user_hash(client: CourtListener) -> str:
    """Return the stable per-user key prefix for the current request.

    OAuth path: reads ``user_hash`` from the FastMCP access-token claims,
    which ``UserInfoTokenVerifier`` populated from the OIDC ``sub`` at
    verification time. The hash survives access-token rotation because it
    is derived from ``sub``, not the raw token.

    Legacy path: hashes the API token directly, matching the old behavior
    for non-OAuth requests.
    """
    try:
        access_token = get_access_token()
    except RuntimeError:
        access_token = None

    if access_token is not None:
        uh = access_token.claims.get("user_hash")
        if uh:
            return uh
        # Should not happen: UserInfoTokenVerifier always sets this. If
        # another verifier is in use, fall through to token-based hashing.

    token = client.api_token or client.access_token
    if not token:
        raise ValueError("Client has no credential; cannot derive user hash.")
    return hmac_hex(token)


def redis_key(client: CourtListener, suffix: str) -> str:
    return f"mcp:{user_hash(client)}:{suffix}"


def make_id() -> str:
    """Generate a short, random UUID for session-scoped tool state."""
    return str(uuid.uuid4())[:8]


async def set_user_scoped(
    client: CourtListener, suffix: str, value: Any
) -> None:
    await get_redis().set(
        redis_key(client, suffix),
        json.dumps(value, default=json_default),
        ex=SESSION_TTL_SECONDS,
    )


async def get_user_scoped(client: CourtListener, suffix: str) -> Any:
    raw = await get_redis().get(redis_key(client, suffix))
    if raw is None:
        return None
    return json.loads(raw)


async def get_session_query(
    query_id: str, client: CourtListener
) -> dict | None:
    return await get_user_scoped(client, f"query:{query_id}")


async def store_session_query(
    query_id: str, data: dict, client: CourtListener
) -> None:
    await set_user_scoped(client, f"query:{query_id}", data)


async def get_session_citation_analysis(
    job_id: str, client: CourtListener
) -> dict | None:
    return await get_user_scoped(client, f"citation:{job_id}")


async def store_session_citation_analysis(
    job_id: str, data: dict, client: CourtListener
) -> None:
    await set_user_scoped(client, f"citation:{job_id}", data)
