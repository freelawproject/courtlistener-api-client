"""Argument schemas and error messages shared by the tag tools."""

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.models.tags import TAG_NAME_MAX_LENGTH, TAG_NAME_PATTERN

TAG_ID_PROPERTY = {
    "type": "integer",
    "description": (
        "ID of one of the user's tags (the `id` from `create_tag`, or from "
        '`call_endpoint` with endpoint_id "tags").'
    ),
}

DOCKET_ID_PROPERTY = {"type": "integer", "description": "ID of the docket."}

TAG_PROPERTIES = {
    "name": {
        "type": "string",
        "pattern": TAG_NAME_PATTERN,
        "maxLength": TAG_NAME_MAX_LENGTH,
        "description": (
            "Short name, unique among the user's tags: letters, numbers, "
            "hyphens and underscores only, e.g. `patent-cases`. It appears "
            "in the tag's URL."
        ),
    },
    "title": {"type": "string", "description": "A longer, readable title."},
    "description": {
        "type": "string",
        "description": "What the tag collects, in Markdown.",
    },
    "published": {
        "type": "boolean",
        "description": (
            "Whether anyone can see the tag and its dockets. Tags are "
            "private unless published."
        ),
    },
}


def is_duplicate(e: CourtListenerAPIError) -> bool:
    """Whether a 400 is the API refusing a duplicate (a unique set)."""
    return e.status_code == 400 and "unique set" in str(e.detail)


def tag_access_message(e: CourtListenerAPIError, tag_id: int) -> str | None:
    """A message for a tag the user can't change, or None to re-raise.

    Another user's published tag is visible, so changing it is refused
    with a 403; anyone else's private tag is invisible, a 404."""
    if e.status_code == 404:
        return f"No tag found with id {tag_id}."
    if e.status_code == 403:
        return (
            f"Tag {tag_id} belongs to another user. You can only change "
            "your own tags."
        )
    return None
