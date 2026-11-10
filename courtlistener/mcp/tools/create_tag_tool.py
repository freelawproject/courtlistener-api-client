from mcp.types import ToolAnnotations

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.tag_utils import (
    TAG_PROPERTIES,
    is_duplicate,
)


class CreateTagTool(MCPTool):
    """Create a tag on CourtListener: a named collection of dockets.

    Tags are private unless published. Returns the new tag; pass its
    `id` to `add_docket_to_tag` to add dockets to it.

    Use `call_endpoint` with endpoint_id "tags" to list tags. The list
    includes other users' published tags, which can be read but not
    changed; `published=false` lists only the user's own private tags.
    """

    name: str = "create_tag"
    annotations: ToolAnnotations = ToolAnnotations(
        title="Create Tag",
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=True,
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": TAG_PROPERTIES,
            "required": ["name"],
            "additionalProperties": False,
        }

    async def call(self, arguments: dict) -> dict | str:
        name = arguments["name"]

        async with self.get_client() as client:
            try:
                return await client.tags.create(
                    name=name,
                    title=arguments.get("title"),
                    description=arguments.get("description"),
                    published=arguments.get("published"),
                )
            except CourtListenerAPIError as e:
                if e.status_code != 400:
                    raise
                if is_duplicate(e):
                    return f"You already have a tag named {name!r}."
                return f"Could not create tag: {e.detail}"
