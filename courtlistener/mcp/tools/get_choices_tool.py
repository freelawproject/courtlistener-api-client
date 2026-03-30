import json

from mcp.types import CallToolResult, TextContent, ToolAnnotations

from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.models import ENDPOINTS


class GetChoicesTool(MCPTool):
    """Get the valid choices for a field on a CourtListener API endpoint.

    Use this when a field's schema says to look up choices with this tool.
    """

    name: str = "get_choices"
    annotations = ToolAnnotations(
        readOnlyHint=True,
        openWorldHint=False,
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "endpoint_id": {
                    "type": "string",
                    "description": "The endpoint ID (e.g. 'courts', 'search', 'dockets').",
                },
                "field_name": {
                    "type": "string",
                    "description": "The field name to get choices for.",
                },
            },
            "required": ["endpoint_id", "field_name"],
        }

    def __call__(self, arguments: dict, session: dict) -> CallToolResult:
        endpoint_id: str = arguments["endpoint_id"]
        field_name: str = arguments["field_name"]

        for endpoint in ENDPOINTS.values():
            if endpoint.endpoint_id != endpoint_id:
                continue

            field_info = endpoint.model_fields.get(field_name)
            if field_info is None:
                return CallToolResult(
                    content=[
                        TextContent(
                            type="text",
                            text=f"Field '{field_name}' not found on endpoint '{endpoint_id}'",
                        )
                    ],
                    isError=True,
                )

            extra = getattr(field_info, "json_schema_extra", {}) or {}
            choices = extra.get("choices", [])
            if not choices:
                return CallToolResult(
                    content=[
                        TextContent(
                            type="text",
                            text=f"Field '{field_name}' on endpoint '{endpoint_id}' has no choices",
                        )
                    ],
                    isError=True,
                )

            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=json.dumps(choices, indent=2),
                    )
                ]
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
