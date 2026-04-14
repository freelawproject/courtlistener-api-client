from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from courtlistener.mcp.tools.mcp_tool import MCPTool


class SubscribeToDocketAlertTool(MCPTool):
    """Subscribe to alerts for a docket on CourtListener.

    Use `call_endpoint` with endpoint_id "docket-alerts" to list
    existing subscriptions.
    """

    name: str = "subscribe_to_docket_alert"
    annotations = ToolAnnotations(
        title="Subscribing to Docket Alert",
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

    async def __call__(self, arguments: dict, ctx: Context) -> dict:
        docket = arguments["docket"]

        with self.get_client() as client:
            alert = client.docket_alerts.subscribe(docket)
            return alert
