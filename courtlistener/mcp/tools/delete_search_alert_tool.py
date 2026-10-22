from mcp.types import ToolAnnotations

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.tools.mcp_tool import MCPTool


class DeleteSearchAlertTool(MCPTool):
    """Delete a search alert on CourtListener.

    Use `call_endpoint` with endpoint_id "alerts" to list existing alerts.
    """

    name: str = "delete_search_alert"
    annotations: ToolAnnotations = ToolAnnotations(
        title="Delete Search Alert",
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=True,
        open_world_hint=True,
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
            "additionalProperties": False,
        }

    async def call(self, arguments: dict) -> str:
        alert_id = arguments["id"]

        async with self.get_client() as client:
            try:
                await client.alerts.delete(alert_id)
            except CourtListenerAPIError as e:
                if e.status_code == 404:
                    return f"No alert found with id {alert_id}."
                raise
            return f"Deleted search alert {alert_id}."
