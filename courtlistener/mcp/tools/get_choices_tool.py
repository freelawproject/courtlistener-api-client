from mcp.types import ToolAnnotations

from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.utils import LONG_CHOICE_FIELDS, long_choices


class GetChoicesTool(MCPTool):
    """List every valid value for a field whose choices are too long to
    include in its schema.

    Only the fields named in `field_name` need this; every other choice
    field lists its values in the schema where it appears.
    """

    name: str = "get_choices"
    annotations: ToolAnnotations = ToolAnnotations(
        title="Get Field Choices",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )

    def get_input_schema(self) -> dict:
        fields = ", ".join(
            f"`{name}` ({', '.join(endpoints)})"
            for name, endpoints in sorted(LONG_CHOICE_FIELDS.items())
        )
        return {
            "type": "object",
            "properties": {
                "field_name": {
                    "type": "string",
                    "enum": sorted(LONG_CHOICE_FIELDS),
                    "description": f"The field to list choices for: {fields}.",
                },
            },
            "required": ["field_name"],
            "additionalProperties": False,
        }

    async def call(self, arguments: dict) -> dict[str, list[dict]]:
        return {"choices": long_choices(arguments["field_name"])}
