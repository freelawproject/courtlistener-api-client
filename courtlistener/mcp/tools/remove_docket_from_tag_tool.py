from mcp.types import ToolAnnotations

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.tag_utils import (
    DOCKET_ID_PROPERTY,
    TAG_ID_PROPERTY,
)


class RemoveDocketFromTagTool(MCPTool):
    """Remove a docket from one of the user's tags on CourtListener.

    Looks the docket up in the tag by docket ID, so you don't need the
    docket tag's own ID. The tag and the docket themselves are untouched.

    Use `call_endpoint` with endpoint_id "docket-tags" to see which
    dockets are in a tag (filter by `tag`).
    """

    name: str = "remove_docket_from_tag"
    annotations: ToolAnnotations = ToolAnnotations(
        title="Remove Docket from Tag",
        read_only_hint=False,
        destructive_hint=True,
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

    async def call(self, arguments: dict) -> str:
        tag_id = arguments["tag_id"]
        docket_id = arguments["docket_id"]

        async with self.get_client() as client:
            try:
                await client.docket_tags.remove(tag_id, docket_id)
            except ValueError:
                return f"Docket {docket_id} isn't in tag {tag_id}."
            except CourtListenerAPIError as e:
                if e.status_code != 403:
                    raise
                return (
                    f"Tag {tag_id} belongs to another user. You can only "
                    "change your own tags."
                )
            return f"Removed docket {docket_id} from tag {tag_id}."
