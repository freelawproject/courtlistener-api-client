import json
from itertools import islice

import tiktoken

from courtlistener.resource import ResourceIterator


def prepare_query_id(response: ResourceIterator, session: dict) -> int:
    if "queries" not in session:
        session["queries"] = {}
    queries = session["queries"]
    query_id = max(queries.keys(), default=0) + 1
    queries[query_id] = {
        "iterator": response,
        "iter": iter(response),
        "returned_count": 0,
    }
    return query_id


def collect_results(query_entry: dict, num_results: int) -> list[dict]:
    results = list(islice(query_entry["iter"], num_results))
    query_entry["returned_count"] += len(results)
    return results


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
