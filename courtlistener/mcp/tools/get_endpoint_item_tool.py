import json

from mcp.types import CallToolResult, TextContent

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.models import ENDPOINTS


class GetEndpointItemTool(MCPTool):
    """Get an item by ID from a CourtListener API endpoint."""

    name: str = "get_endpoint_item"

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

    def __call__(self, arguments: dict, session: dict) -> CallToolResult:
        """Call the get_endpoint_item tool."""
        endpoint_id = arguments.get("endpoint_id")
        item_id = arguments.get("item_id")
        fields = arguments.get("fields")

        if not isinstance(item_id, int | str):
            return CallToolResult(
                content=[
                    TextContent(
                        type="text", text="Item ID must be a string or integer"
                    )
                ],
                isError=True,
            )

        for endpoint_name, endpoint in ENDPOINTS.items():
            if endpoint.endpoint_id == endpoint_id:
                with self.get_client() as client:
                    resource = getattr(client, endpoint_name)
                    try:
                        item = resource.get(item_id, fields=fields)
                        item_str = json.dumps(item, indent=2)
                        return CallToolResult(
                            content=[TextContent(type="text", text=item_str)]
                        )
                    except (ValueError, CourtListenerAPIError) as exc:
                        return CallToolResult(
                            content=[TextContent(type="text", text=str(exc))],
                            isError=True,
                        )

        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=f"Endpoint '{endpoint_id}' not found",
                )
            ],
            isError=True,
        )
