from mcp.types import ToolAnnotations

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.tag_utils import (
    DOCKET_ID_PROPERTY,
    TAG_ID_PROPERTY,
    is_duplicate,
)


class AddDocketToTagTool(MCPTool):
    """Add a docket to one of the user's tags on CourtListener.

    Does nothing if the docket is already in the tag; the result then has
    `already_tagged` set. To start a new tag, use `create_tag` first.

    Use `call_endpoint` with endpoint_id "docket-tags" to see which
    dockets are in a tag (filter by `tag`).
    """

    name: str = "add_docket_to_tag"
    annotations: ToolAnnotations = ToolAnnotations(
        title="Add Docket to Tag",
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=True,
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "tag_id": TAG_ID_PROPERTY,
                "docket_id": DOCKET_ID_PROPERTY,
            },
            "required": ["tag_id", "docket_id"],
            "additionalProperties": False,
        }

    async def call(self, arguments: dict) -> dict | str:
        tag_id = arguments["tag_id"]
        docket_id = arguments["docket_id"]

        async with self.get_client() as client:
            try:
                return await client.docket_tags.add(tag_id, docket_id)
            except CourtListenerAPIError as e:
                if e.status_code != 400:
                    raise
                if is_duplicate(e):
                    return f"Docket {docket_id} is already in tag {tag_id}."
                detail = e.detail if isinstance(e.detail, dict) else {}
                # The API only accepts the user's own tags here, so
                # another user's tag is as unknown as a missing one.
                if "tag" in detail:
                    return (
                        f"You have no tag with id {tag_id}. Create one "
                        "with `create_tag`."
                    )
                if "docket" in detail:
                    return f"No docket found with id {docket_id}."
                return (
                    f"Could not add docket {docket_id} to tag {tag_id}: "
                    f"{e.detail}"
                )
