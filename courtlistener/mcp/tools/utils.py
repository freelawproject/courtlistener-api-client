import json
import logging
import re
import uuid
from itertools import islice

import tiktoken

from courtlistener import CourtListener
from courtlistener.mcp.session import get_session
from courtlistener.mcp.settings import DEFAULT_NUM_RESULTS
from courtlistener.models import ENDPOINTS
from courtlistener.resource import ResourceIterator

logger = logging.getLogger(__name__)


def normalize_fields(fields):
    """Accept comma- or space-separated `fields` strings."""
    if isinstance(fields, str):
        return [f for f in re.split(r"[,\s]+", fields.strip(" ,")) if f]
    return fields


def endpoint_id_choices(include_search: bool = False) -> list[str]:
    """Valid endpoint_id values."""
    choices = []
    for endpoint in ENDPOINTS.values():
        endpoint_id = endpoint.endpoint_id
        is_search = endpoint_id == "search" or endpoint_id.endswith("-search")
        if is_search and not include_search:
            continue
        choices.append(endpoint_id)
    return choices


def endpoint_id_property(
    description: str, include_search: bool = False
) -> dict:
    """Build the endpoint_id schema property."""
    return {
        "type": "string",
        "enum": endpoint_id_choices(include_search=include_search),
        "description": description,
    }


def collect_results(
    response: ResourceIterator, num_results: int = DEFAULT_NUM_RESULTS
) -> list[dict]:
    """Consume up to *num_results* items from a ResourceIterator."""
    return list(islice(response, num_results))


async def prepare_query_id(
    response: ResourceIterator,
    client: CourtListener,
    fields: list[str] | None = None,
) -> str:
    """Store the query response and return a short UUID query ID."""
    query_id = make_id()
    data: dict = {"response": response.dump()}
    if fields is not None:
        data["fields"] = fields
    await get_session().store_query(query_id, data, client)
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
    filtered = [
        {
            k: v
            for k, v in r.items()
            # Always keep opinion_id to avoid cluster_id confusion
            if k in fields or k == "opinion_id"
        }
        for r in results
    ]
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


def inline_refs(node, defs, seen=None):
    """Recursively replace JSON-Schema ``$ref`` pointers with their definitions."""
    if isinstance(node, list):
        return [inline_refs(item, defs, seen) for item in node]
    if not isinstance(node, dict):
        return node

    ref = node.get("$ref")
    if ref is not None:
        name = ref.rsplit("/", 1)[-1]
        nodes_seen = seen or frozenset()
        if name in nodes_seen:
            return {"type": "object"}
        target = defs.get(name, {})
        resolved = inline_refs(target, defs, nodes_seen | {name})
        siblings = {
            key: inline_refs(value, defs, seen)
            for key, value in node.items()
            if key != "$ref"
        }
        return {**resolved, **siblings}

    return {key: inline_refs(value, defs, seen) for key, value in node.items()}


def strip_schema_keys(node, keys):
    """Recursively drop ``keys`` from every dict in a schema tree."""
    if isinstance(node, list):
        return [strip_schema_keys(item, keys) for item in node]
    if isinstance(node, dict):
        return {
            key: strip_schema_keys(value, keys)
            for key, value in node.items()
            if key not in keys
        }
    return node


def prepare_filter(filter, endpoint_id: str = "", field_name: str = ""):
    choices_str = prepare_choices_str(
        filter.get("choices"),
        endpoint_id=endpoint_id,
        field_name=field_name,
    )
    filter["description"] = (
        filter.get("description", "") + "\n\n" + choices_str
    ).strip()
    if "choices" in filter:
        del filter["choices"]
    return strip_schema_keys(
        filter, {"title", "related_class_name", "default"}
    )


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


def make_id() -> str:
    """Generate a short, random UUID for session-scoped tool state."""
    return str(uuid.uuid4())[:8]


async def fetch_document_text(
    doc_type: str, doc_id: int, client: CourtListener
) -> str | None:
    """Return full document text, fetching from the API on cache miss."""
    doc_types = {
        "opinion": ("opinions", "html_with_citations"),
        "recap_document": ("recap_documents", "plain_text"),
    }
    if doc_type not in doc_types:
        raise ValueError(f"Unknown doc_type: {doc_type!r}")

    session = get_session()
    cached = await session.get_document(doc_type, doc_id)
    if cached is not None:
        return cached

    resource_name, field = doc_types[doc_type]
    item = getattr(client, resource_name).get(doc_id, fields=[field])
    text = item.get(field) or ""

    if text:
        await session.store_document(doc_type, doc_id, text)

    return text or None


ORDERED_OPINION_TYPES = (
    ("020lead", "lead-opinion"),
    ("010combined", "combined-opinion"),
    ("015unamimous", "unanimous-opinion"),  # misspelled in the API
    ("025plurality", "plurality-opinion"),
    ("080onthemerits", "on-the-merits"),
)
OPINION_TYPE_RANK = {
    spelling: rank
    for rank, spellings in enumerate(ORDERED_OPINION_TYPES)
    for spelling in spellings
}


def opinion_sort_key(opinion: dict) -> tuple[int, int, int]:
    """Rank an opinion so the court's main opinion sorts first."""
    ordering_key = opinion.get("ordering_key")
    opinion_type: str = opinion.get("type") or ""
    return (
        ordering_key if isinstance(ordering_key, int) else 99999,
        OPINION_TYPE_RANK.get(opinion_type, len(ORDERED_OPINION_TYPES)),
        opinion.get("id") or 0,
    )


def add_opinion_ids(results: list[dict]) -> None:
    """Copy each opinion search result's main opinion id to top level."""
    for result in results:
        opinions = [
            opinion
            for opinion in result.get("opinions") or []
            if isinstance(opinion, dict) and opinion.get("id") is not None
        ]
        if opinions:
            main = min(opinions, key=opinion_sort_key)
            result.setdefault("opinion_id", main["id"])


def resolve_cluster_opinion_ids(
    cluster_id: int, client: CourtListener
) -> list[int]:
    """Return a cluster's opinion ids, main opinion first."""
    response = client.opinions.list(
        cluster=cluster_id, fields=["id", "type", "ordering_key"]
    )
    opinions = [
        opinion
        for opinion in collect_results(response, 20)
        if opinion.get("id") is not None
    ]
    if not opinions:
        raise ValueError(f"Cluster {cluster_id} has no opinions.")
    opinions.sort(key=opinion_sort_key)
    return [opinion["id"] for opinion in opinions]
