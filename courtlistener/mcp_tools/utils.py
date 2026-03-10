import json
from itertools import islice

import tiktoken

from courtlistener.resource import ResourceIterator


def prepare_query_id(response: ResourceIterator, session: dict) -> int:
    """Store a ResourceIterator in the session and return a query ID.

    The iterator object is stored directly so that it can be used later
    for count resolution (via ``response.count``) and continued
    pagination (via ``get_more_results``).
    """
    if "queries" not in session:
        session["queries"] = {}
    queries = session["queries"]
    if len(queries) == 0:
        query_id = 1
    else:
        query_id = max(queries.keys()) + 1
    # Store the live iterator and a generator for continued iteration.
    queries[query_id] = {
        "iterator": response,
        "generator": iter(response),
    }
    return query_id


def collect_results(session: dict, query_id: int, num_results: int) -> list[dict]:
    """Collect up to *num_results* items from the stored generator."""
    query = session["queries"].get(query_id)
    if query is None:
        return []
    return list(islice(query["generator"], num_results))


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


def prepare_count_str(count: int | str | None, query_id: int) -> str:
    if isinstance(count, int):
        count_str = f"Total count: {count}"
    elif isinstance(count, str):
        count_str = (
            f"To get the count use the `get_counts` tool with "
            f'query_id="{query_id}".'
        )
    else:
        count_str = ""
    return count_str
