import json

from mcp.types import CallToolResult, TextContent

from courtlistener.mcp_tools.mcp_tool import MCPTool
from courtlistener.models import ENDPOINTS


class CallEndpointTool(MCPTool):
    """Call CourtListener API endpoint.

    Use this for additional API endpoints which do not have a
    dedicated MCP tool. These endpoints are distinct from the
    search endpoint and often include more detailed metadata.
    """

    name: str = "call_endpoint"

    def get_input_schema(self) -> dict:
        """Get the input schema for the call_endpoint tool."""
        return {
            "type": "object",
            "properties": {
                "endpoint_id": {
                    "type": "string",
                    "description": "Endpoint ID to call (see `get_endpoint_schema` tool for valid endpoint IDs)",
                },
                "query": {
                    "type": "object",
                    "description": "Should match the endpoint schema returned by the `get_endpoint_schema` tool.",
                    "additionalProperties": True,
                },
            },
            "required": ["endpoint_id"],
        }

    def __call__(
        self, arguments: dict, session: dict
    ) -> list[TextContent] | CallToolResult:
        """Call the call_endpoint tool."""
        endpoint_id = arguments.get("endpoint_id")
        query = arguments.get("query") or {}
        for endpoint_name, endpoint in ENDPOINTS.items():
            if endpoint.endpoint_id == endpoint_id:
                with self.get_client() as client:
                    resource = getattr(client, endpoint_name)
                    response = resource.list(**query)
                    return [
                        TextContent(
                            type="text",
                            text=json.dumps(response.results, indent=2),
                        )
                    ]
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=f"Endpoint '{endpoint_id}' not found",
                )
            ],
            isError=True,
        )
