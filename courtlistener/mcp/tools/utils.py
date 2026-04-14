import json
import uuid
from itertools import islice

import tiktoken
from fastmcp.server.context import Context

from courtlistener.resource import ResourceIterator

DEFAULT_NUM_RESULTS = 20
MAX_NUM_RESULTS = 100


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
    ctx: Context,
    fields: list[str] | None = None,
) -> str:
    """Store query response in session and return a short UUID query ID."""
    query_id = make_id()
    data: dict = {"response": response.dump()}
    if fields is not None:
        data["fields"] = fields
    await store_session_query(query_id, data, ctx)
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


# Session store helpers
def make_id() -> str:
    return str(uuid.uuid4())[:8]


async def get_session_query(query_id: str, ctx: Context) -> dict | None:
    return await ctx.get_state(f"query:{query_id}")


async def store_session_query(query_id: str, data: dict, ctx: Context) -> None:
    await ctx.set_state(f"query:{query_id}", data)


async def get_session_citation_analysis(
    job_id: str, ctx: Context
) -> dict | None:
    return await ctx.get_state(f"citation:{job_id}")


async def store_session_citation_analysis(
    job_id: str, data: dict, ctx: Context
) -> None:
    await ctx.set_state(f"citation:{job_id}", data)
