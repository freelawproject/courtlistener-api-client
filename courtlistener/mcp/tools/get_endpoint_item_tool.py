from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.models import ENDPOINTS


class GetEndpointItemTool(MCPTool):
    """Get an item by ID from a CourtListener API endpoint."""

    name: str = "get_endpoint_item"
    annotations = ToolAnnotations(
        title="Get Item by ID",
        readOnlyHint=True,
        openWorldHint=True,
    )

    def get_input_schema(self) -> dict:
        """Get the input schema for the get_endpoint_item tool."""
        return {
            "type": "object",
            "properties": {
                "endpoint_id": {
                    "type": "string",
                    "description": "Endpoint ID to get an item from",
                },
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
                        {"type": "null"},
                    ],
                    "description": "Filter which fields are returned.",
                },
            },
            "required": ["endpoint_id", "item_id"],
        }

    async def __call__(self, arguments: dict, ctx: Context) -> dict:
        """Call the get_endpoint_item tool."""
        endpoint_id = arguments.get("endpoint_id")
        item_id = arguments.get("item_id")
        fields = arguments.get("fields")

        if not isinstance(item_id, int | str):
            raise ValueError("Item ID must be a string or integer")

        for endpoint_name, endpoint in ENDPOINTS.items():
            if endpoint.endpoint_id == endpoint_id:
                with self.get_client() as client:
                    resource = getattr(client, endpoint_name)
                    item = resource.get(item_id, fields=fields)
                    return item

        raise ValueError(f"Endpoint '{endpoint_id}' not found")
