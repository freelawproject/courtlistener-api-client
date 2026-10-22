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
    annotations: ToolAnnotations = ToolAnnotations(
        title="Unsubscribe from Docket Alert",
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=True,
        open_world_hint=True,
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
            "additionalProperties": False,
        }

    async def call(self, arguments: dict) -> str:
        docket = arguments["docket"]

        async with self.get_client() as client:
            await client.docket_alerts.unsubscribe(docket)
            return f"Unsubscribed from docket alert for docket {docket}."
