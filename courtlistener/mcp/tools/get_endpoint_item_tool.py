from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.utils import (
    endpoint_id_property,
    normalize_fields,
)
from courtlistener.models import ENDPOINTS


class GetEndpointItemTool(MCPTool):
    """Get an item by ID from a CourtListener API endpoint."""

    name: str = "get_endpoint_item"
    annotations = ToolAnnotations(
        title="Get Item by ID",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )

    def get_input_schema(self) -> dict:
        """Get the input schema for the get_endpoint_item tool."""
        return {
            "type": "object",
            "properties": {
                "endpoint_id": endpoint_id_property(
                    "The endpoint to get an item from."
                ),
                "item_id": {
                    "anyOf": [
                        {"type": "string"},
                        {"type": "integer"},
                    ],
                    "description": "The ID of the item to get.",
                },
                "fields": {
                    "anyOf": [
                        {"type": "array", "items": {"type": "string"}},
                        {"type": "string"},
                        {"type": "null"},
                    ],
                    "description": (
                        "Filter which fields are returned. Use the field "
                        "names from the endpoint's own schema (see the "
                        "`get_endpoint_schema` tool), not the field names "
                        "returned by the `search` tool."
                    ),
                },
            },
            "required": ["endpoint_id", "item_id"],
            "additionalProperties": False,
        }

    async def __call__(self, arguments: dict, ctx: Context) -> dict:
        """Call the get_endpoint_item tool."""
        endpoint_id = arguments.get("endpoint_id")
        item_id = arguments.get("item_id")
        fields = normalize_fields(arguments.get("fields"))

        for endpoint_name, endpoint in ENDPOINTS.items():
            if endpoint.endpoint_id == endpoint_id:
                async with self.get_client() as client:
                    resource = getattr(client, endpoint_name)
                    item = await resource.get(item_id, fields=fields)
                    return item

        # Unreachable: the schema's endpoint_id enum is validated in
        # ToolHandlerMiddleware before dispatch. Guards the fall-through.
        raise ValueError(f"Endpoint '{endpoint_id}' not found")
