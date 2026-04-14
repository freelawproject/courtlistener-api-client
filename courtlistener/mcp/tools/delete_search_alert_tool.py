from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from courtlistener.mcp.tools.mcp_tool import MCPTool


class DeleteSearchAlertTool(MCPTool):
    """Delete a search alert on CourtListener.

    Use `call_endpoint` with endpoint_id "alerts" to list existing alerts.
    """

    name: str = "delete_search_alert"
    annotations = ToolAnnotations(
        title="Deleting Search Alert",
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

    async def __call__(self, arguments: dict, ctx: Context) -> str:
        alert_id = arguments["id"]

        with self.get_client() as client:
            client.alerts.delete(alert_id)
            return f"Deleted search alert {alert_id}."
