from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from courtlistener.mcp.tools.mcp_tool import MCPTool


class UnsubscribeFromDocketAlertTool(MCPTool):
    """Unsubscribe from alerts for a docket on CourtListener.

    Looks up the alert by docket ID and deletes it, so you only need
    the docket ID (not the alert ID).

    Use `call_endpoint` with endpoint_id "docket-alerts" to list
    existing subscriptions.
    """

    name: str = "unsubscribe_from_docket_alert"
    annotations = ToolAnnotations(
        title="Unsubscribing from Docket Alert",
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=True,
        openWorldHint=True,
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "docket": {
                    "type": "integer",
                    "description": "The docket ID to unsubscribe from.",
                },
            },
            "required": ["docket"],
        }

    async def __call__(self, arguments: dict, ctx: Context) -> str:
        docket = arguments["docket"]

        with self.get_client() as client:
            client.docket_alerts.unsubscribe(docket)
            return f"Unsubscribed from docket alert for docket {docket}."
