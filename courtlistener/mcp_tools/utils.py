import json

import tiktoken

from courtlistener import CourtListener


def get_client() -> CourtListener:
    """Get a CourtListener client instance."""
    return CourtListener()


def prepare_choices_str(choices, max_tokens=1000):
    if not choices:
        return ""

    choices_str = json.dumps(choices, indent=2)
    num_tokens = len(
        tiktoken.encoding_for_model("gpt-5-mini").encode(choices_str)
    )
    if num_tokens > max_tokens:
        return ""  # TODO: Show a snippet and direct model to use get_choices tool

    choices_str = "Valid choices:\n\n" + choices_str
    return choices_str


def prepare_filter(filter):
    # Prepare filter description
    choices_str = prepare_choices_str(filter.get("choices"))
    filter["description"] = (
        filter.get("description", "") + "\n\n" + choices_str
    ).strip()
    # Remove unnecessary keys
    for key in ["choices", "title", "related_class_name", "default"]:
        if key in filter:
            del filter[key]
    return filter
