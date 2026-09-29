from typing import Any

from mcp.types import ToolAnnotations

from courtlistener.mcp.settings import (
    DEFAULT_NUM_RESULTS,
    MAX_NUM_RESULTS,
)
from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.utils import (
    collect_results,
    endpoint_id_property,
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
    annotations: ToolAnnotations = ToolAnnotations(
        title="Call API Endpoint",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )

    def get_input_schema(self) -> dict:
        """Get the input schema for the call_endpoint tool."""
        return {
            "type": "object",
            "properties": {
                "endpoint_id": endpoint_id_property("The endpoint to call."),
                "query": {
                    "type": "object",
                    "description": (
                        "Should match the endpoint schema returned by the "
                        "`get_endpoint_schema` tool. Every endpoint "
                        "parameter goes in here, including `fields` — "
                        "unlike the `search` tool, this tool takes no "
                        "top-level `fields` argument. Do not put "
                        "`page_size` or `num_results` in here; to control "
                        "how many results come back, use the top-level "
                        "`num_results` argument."
                    ),
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
            "additionalProperties": False,
        }

    async def call(self, arguments: dict) -> Any:
        """Call the call_endpoint tool."""
        endpoint_id = arguments.get("endpoint_id")
        query = arguments.get("query") or {}
        num_results = arguments.get("num_results", DEFAULT_NUM_RESULTS)
        for endpoint_name, endpoint in ENDPOINTS.items():
            if endpoint.endpoint_id == endpoint_id:
                async with self.get_client() as client:
                    resource = getattr(client, endpoint_name)
                    response = resource.list(**query)

                    results = await collect_results(response, num_results)
                    query_id = await prepare_query_id(response)
                    current_page = await response.get_current_page()
                    count = prepare_count(current_page.count, query_id)

                    outputs = {
                        "query_id": query_id,
                        "count": count,
                        "results": results,
                    }

                    has_more_str = await prepare_has_more_str(
                        response, query_id
                    )
                    if has_more_str is not None:
                        outputs["has_more"] = has_more_str
                    return outputs
        raise ValueError(f"Endpoint '{endpoint_id}' not found")
