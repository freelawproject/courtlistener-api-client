import json

from mcp.types import CallToolResult, TextContent

from courtlistener.mcp_tools.mcp_tool import MCPTool
from courtlistener.mcp_tools.utils import (
    DEFAULT_NUM_RESULTS,
    MAX_NUM_RESULTS,
    collect_results,
    prepare_count_str,
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

    def __call__(self, arguments: dict, session: dict) -> CallToolResult:
        """Call the call_endpoint tool."""
        endpoint_id = arguments.get("endpoint_id")
        query = arguments.get("query") or {}
        num_results = arguments.get("num_results", DEFAULT_NUM_RESULTS)
        for endpoint_name, endpoint in ENDPOINTS.items():
            if endpoint.endpoint_id == endpoint_id:
                with self.get_client() as client:
                    resource = getattr(client, endpoint_name)
                    response = resource.list(**query)

                    # Collect results first so page_result_index is
                    # updated before we dump state.
                    results = collect_results(response, num_results)

                    query_id = prepare_query_id(response, session)
                    outputs = [f"Query ID: {query_id}"]

                    count_str = prepare_count_str(
                        response.current_page.count, query_id
                    )
                    outputs.append(count_str)

                    results_str = json.dumps(results, indent=2)
                    outputs.append(results_str)

                    has_more_str = prepare_has_more_str(response, query_id)
                    outputs.append(has_more_str)

                    outputs_str = "\n\n".join(
                        [x for x in outputs if x]
                    ).strip()
                    return CallToolResult(
                        content=[TextContent(type="text", text=outputs_str)]
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
