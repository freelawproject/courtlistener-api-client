from mcp.types import CallToolResult, TextContent, ToolAnnotations

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.tools.mcp_tool import MCPTool


class DeleteSearchAlertTool(MCPTool):
    """Delete a search alert on CourtListener.

    Use `call_endpoint` with endpoint_id "alerts" to list existing alerts.
    """

    name: str = "delete_search_alert"
    annotations = ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=True,
        openWorldHint=True,
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "id": {
                    "type": "integer",
                    "description": "The ID of the search alert to delete.",
                },
            },
            "required": ["id"],
        }

    def __call__(self, arguments: dict, session: dict) -> CallToolResult:
        alert_id = arguments["id"]

        try:
            with self.get_client() as client:
                client.alerts.delete(alert_id)
                return CallToolResult(
                    content=[
                        TextContent(
                            type="text",
                            text=f"Deleted search alert {alert_id}.",
                        )
                    ]
                )
        except (ValueError, CourtListenerAPIError) as exc:
            return CallToolResult(
                content=[TextContent(type="text", text=str(exc))],
                isError=True,
            )
