import json

from mcp.types import CallToolResult, TextContent

from courtlistener.mcp_tools.mcp_tool import MCPTool
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
            },
            "required": ["endpoint_id", "item_id"],
        }

    def __call__(self, arguments: dict, session: dict) -> CallToolResult:
        """Call the get_endpoint_item tool."""
        endpoint_id = arguments.get("endpoint_id")
        item_id = arguments.get("item_id")

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
                    item = resource.get(item_id)
                    item_str = json.dumps(item, indent=2)
                    return CallToolResult(
                        content=[TextContent(type="text", text=item_str)]
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
