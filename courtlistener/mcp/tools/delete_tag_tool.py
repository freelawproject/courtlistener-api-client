from mcp.types import ToolAnnotations

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.tag_utils import (
    TAG_ID_PROPERTY,
    tag_access_message,
)


class DeleteTagTool(MCPTool):
    """Delete one of the user's tags on CourtListener.

    This removes the tag from every docket in it; the dockets themselves
    are untouched. To take a single docket out of a tag, use
    `remove_docket_from_tag` instead.

    Use `call_endpoint` with endpoint_id "tags" to list tags.
    """

    name: str = "delete_tag"
    annotations: ToolAnnotations = ToolAnnotations(
        title="Delete Tag",
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=True,
        open_world_hint=True,
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {"tag_id": TAG_ID_PROPERTY},
            "required": ["tag_id"],
            "additionalProperties": False,
        }

    async def call(self, arguments: dict) -> str:
        tag_id = arguments["tag_id"]

        async with self.get_client() as client:
            try:
                await client.tags.delete(tag_id)
            except CourtListenerAPIError as e:
                message = tag_access_message(e, tag_id)
                if message is None:
                    raise
                return message
            return f"Deleted tag {tag_id}."
