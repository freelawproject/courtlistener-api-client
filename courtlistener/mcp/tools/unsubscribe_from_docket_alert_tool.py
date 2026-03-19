from mcp.types import CallToolResult, TextContent

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.tools.mcp_tool import MCPTool


class UnsubscribeFromDocketAlertTool(MCPTool):
    """Unsubscribe from alerts for a docket on CourtListener.

    Looks up the alert by docket ID and deletes it, so you only need
    the docket ID (not the alert ID).

    Use `call_endpoint` with endpoint_id "docket-alerts" to list
    existing subscriptions.
    """

    name: str = "unsubscribe_from_docket_alert"

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

    def __call__(self, arguments: dict, session: dict) -> CallToolResult:
        docket = arguments["docket"]

        try:
            with self.get_client() as client:
                client.docket_alerts.unsubscribe(docket)
                return CallToolResult(
                    content=[
                        TextContent(
                            type="text",
                            text=(
                                f"Unsubscribed from docket alert "
                                f"for docket {docket}."
                            ),
                        )
                    ]
                )
        except (ValueError, CourtListenerAPIError) as exc:
            return CallToolResult(
                content=[TextContent(type="text", text=str(exc))],
                isError=True,
            )
