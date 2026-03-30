import json

from mcp.types import CallToolResult, TextContent, ToolAnnotations

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.tools.mcp_tool import MCPTool


class SubscribeToDocketAlertTool(MCPTool):
    """Subscribe to alerts for a docket on CourtListener.

    Use `call_endpoint` with endpoint_id "docket-alerts" to list
    existing subscriptions.
    """

    name: str = "subscribe_to_docket_alert"
    annotations = ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "docket": {
                    "type": "integer",
                    "description": "The docket ID to subscribe to.",
                },
            },
            "required": ["docket"],
        }

    def __call__(self, arguments: dict, session: dict) -> CallToolResult:
        docket = arguments["docket"]

        try:
            with self.get_client() as client:
                alert = client.docket_alerts.subscribe(docket)
                return CallToolResult(
                    content=[
                        TextContent(
                            type="text",
                            text=json.dumps(alert, indent=2),
                        )
                    ]
                )
        except (ValueError, CourtListenerAPIError) as exc:
            return CallToolResult(
                content=[TextContent(type="text", text=str(exc))],
                isError=True,
            )
