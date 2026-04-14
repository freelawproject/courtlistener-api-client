from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.utils import prepare_filter
from courtlistener.models import ENDPOINTS


class GetEndpointSchemaTool(MCPTool):
    """Get the schema for a CourtListener API endpoint.

    Use this for additional API endpoints which do not have a
    dedicated MCP tool. These endpoints are distinct from the
    search endpoint and often include more detailed metadata.
    """

    name: str = "get_endpoint_schema"
    annotations = ToolAnnotations(
        title="Getting Endpoint Schema",
        readOnlyHint=True,
        openWorldHint=False,
    )

    def get_input_schema(self) -> dict:
        """Get the input schema for the get_endpoint_schema tool."""
        endpoint_ids = []
        for endpoint in ENDPOINTS.values():
            endpoint_id = endpoint.endpoint_id
            if endpoint_id == "search" or endpoint_id.endswith("-search"):
                continue
            endpoint_ids.append(endpoint_id)
        description = "Valid endpoint IDs:\n\t" + "\n\t".join(endpoint_ids)
        return {
            "type": "object",
            "properties": {
                "endpoint_id": {
                    "type": "string",
                    "description": description,
                },
            },
            "required": ["endpoint_id"],
        }

    async def __call__(self, arguments: dict, ctx: Context) -> dict:
        """Call the get_endpoint_schema tool."""
        endpoint_id = arguments.get("endpoint_id")
        for endpoint in ENDPOINTS.values():
            if endpoint.endpoint_id == endpoint_id:
                properties = endpoint.model_json_schema()["properties"]
                updated_properties = {}
                for filter_name, filter in properties.items():
                    if "const" not in filter:
                        updated_properties[filter_name] = prepare_filter(
                            filter,
                            endpoint_id=endpoint_id,
                            field_name=filter_name,
                        )
                schema = {
                    "type": "object",
                    "properties": updated_properties,
                }
                return schema
        raise ValueError(f"Endpoint '{endpoint_id}' not found")
