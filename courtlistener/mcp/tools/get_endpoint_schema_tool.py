from mcp.types import ToolAnnotations

from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.utils import (
    endpoint_id_property,
    inline_refs,
    prepare_filter,
)
from courtlistener.models import ENDPOINTS


class GetEndpointSchemaTool(MCPTool):
    """Get the schema for a CourtListener API endpoint.

    Use this for additional API endpoints which do not have a
    dedicated MCP tool. These endpoints are distinct from the
    search endpoint and often include more detailed metadata.
    """

    name: str = "get_endpoint_schema"
    annotations: ToolAnnotations = ToolAnnotations(
        title="Get Endpoint Schema",
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )

    def get_input_schema(self) -> dict:
        """Get the input schema for the get_endpoint_schema tool."""
        return {
            "type": "object",
            "properties": {
                "endpoint_id": endpoint_id_property(
                    "The endpoint to get the schema for."
                ),
            },
            "required": ["endpoint_id"],
            "additionalProperties": False,
        }

    async def call(self, arguments: dict) -> dict:
        """Call the get_endpoint_schema tool."""
        endpoint_id = arguments.get("endpoint_id")
        for endpoint in ENDPOINTS.values():
            if endpoint.endpoint_id == endpoint_id:
                full_schema = endpoint.model_json_schema()
                defs = full_schema.get("$defs", {})
                properties = full_schema["properties"]
                updated_properties = {}
                for filter_name, filter in properties.items():
                    if "const" not in filter:
                        filter = inline_refs(filter, defs)
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
        # Unreachable: the schema's endpoint_id enum is validated in
        # `MCPTool.run` before dispatch. Guards the fall-through.
        raise ValueError(f"Endpoint '{endpoint_id}' not found")
