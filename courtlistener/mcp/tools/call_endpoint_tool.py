from typing import Any

from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.utils import (
    DEFAULT_NUM_RESULTS,
    MAX_NUM_RESULTS,
    collect_results,
    prepare_count,
    prepare_has_more_str,
    prepare_query_id,
)
from courtlistener.models import ENDPOINTS


class CallEndpointTool(MCPTool):
    """Call CourtListener API endpoint.

    Use this for additional API endpoints which do not have a
    dedicated MCP tool. These endpoints are distinct from the
    search endpoint and often include more detailed metadata.
    """

    name: str = "call_endpoint"
    annotations = ToolAnnotations(
        title="Calling API Endpoint",
        readOnlyHint=True,
        openWorldHint=True,
    )

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
                "num_results": {
                    "type": "integer",
                    "description": (
                        f"Number of results to return (1-{MAX_NUM_RESULTS}). "
                        f"Defaults to {DEFAULT_NUM_RESULTS}."
                    ),
                    "minimum": 1,
                    "maximum": MAX_NUM_RESULTS,
                    "default": DEFAULT_NUM_RESULTS,
                },
            },
            "required": ["endpoint_id"],
        }

    async def __call__(self, arguments: dict, ctx: Context) -> Any:
        """Call the call_endpoint tool."""
        endpoint_id = arguments.get("endpoint_id")
        query = arguments.get("query") or {}
        num_results = arguments.get("num_results", DEFAULT_NUM_RESULTS)
        for endpoint_name, endpoint in ENDPOINTS.items():
            if endpoint.endpoint_id == endpoint_id:
                with self.get_client() as client:
                    resource = getattr(client, endpoint_name)
                    response = resource.list(**query)

                    results = collect_results(response, num_results)
                    query_id = await prepare_query_id(response, ctx)
                    count = prepare_count(
                        response.current_page.count, query_id
                    )

                    outputs = {
                        "query_id": query_id,
                        "count": count,
                        "results": results,
                    }

                    has_more_str = prepare_has_more_str(response, query_id)
                    if has_more_str is not None:
                        outputs["has_more"] = has_more_str
                    return outputs
        raise ValueError(f"Endpoint '{endpoint_id}' not found")
