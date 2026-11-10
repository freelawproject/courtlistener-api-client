from mcp.types import ToolAnnotations

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.tag_utils import (
    TAG_ID_PROPERTY,
    TAG_PROPERTIES,
    is_duplicate,
    tag_access_message,
)


class UpdateTagTool(MCPTool):
    """Change one of the user's tags on CourtListener: rename it, retitle
    or redescribe it, or publish or unpublish it.

    Only the fields you pass change. Publishing a tag lets anyone see it
    and its dockets.

    Use `call_endpoint` with endpoint_id "tags" to list tags.
    """

    name: str = "update_tag"
    annotations: ToolAnnotations = ToolAnnotations(
        title="Update Tag",
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=True,
        open_world_hint=True,
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {"tag_id": TAG_ID_PROPERTY, **TAG_PROPERTIES},
            "required": ["tag_id"],
            "additionalProperties": False,
        }

    async def call(self, arguments: dict) -> dict | str:
        tag_id = arguments["tag_id"]
        changes = {
            field: arguments[field]
            for field in TAG_PROPERTIES
            if arguments.get(field) is not None
        }
        if not changes:
            return (
                "Nothing to change: pass at least one of "
                f"{', '.join(f'`{field}`' for field in TAG_PROPERTIES)}."
            )

        async with self.get_client() as client:
            try:
                return await client.tags.update(tag_id, **changes)
            except CourtListenerAPIError as e:
                message = tag_access_message(e, tag_id)
                if message:
                    return message
                if e.status_code != 400:
                    raise
                if is_duplicate(e):
                    return f"You already have a tag named {changes['name']!r}."
                return f"Could not update tag {tag_id}: {e.detail}"
