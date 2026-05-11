from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.tools.mcp_tool import MCPTool


class CreateSearchAlertTool(MCPTool):
    """Create a search alert on CourtListener.

    Use `call_endpoint` with endpoint_id "alerts" to list existing alerts.
    """

    name: str = "create_search_alert"
    annotations = ToolAnnotations(
        title="Create Search Alert",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "A name for the alert.",
                },
                "query": {
                    "anyOf": [{"type": "string"}, {"type": "object"}],
                    "description": (
                        "Search query as a URL query string "
                        '(e.g. "q=test&court=scotus") or a structured dict '
                        '(e.g. {"q": "test", "court": "scotus"}).'
                    ),
                },
                "rate": {
                    "type": "string",
                    "enum": ["rt", "dly", "wly", "mly", "off"],
                    "description": (
                        "Alert frequency: "
                        '"rt" (real time), "dly" (daily), "wly" (weekly), '
                        '"mly" (monthly), or "off" (disabled).'
                    ),
                },
                "alert_type": {
                    "type": "string",
                    "enum": ["o", "r", "d", "oa"],
                    "description": (
                        "Optional alert type matching the search `type` in "
                        'the query: "o" (opinion), "r" (recap), '
                        '"d" (docket), or "oa" (oral argument). '
                        "If omitted, the server infers it from the query."
                    ),
                },
            },
            "required": ["name", "query", "rate"],
        }

    async def __call__(self, arguments: dict, ctx: Context) -> dict | str:
        name = arguments["name"]
        query = arguments["query"]
        rate = arguments["rate"]
        alert_type = arguments.get("alert_type")

        with self.get_client() as client:
            try:
                return client.alerts.create(
                    name=name,
                    query=query,
                    rate=rate,
                    alert_type=alert_type,
                )
            except CourtListenerAPIError as e:
                if e.status_code != 400:
                    raise
                return f"Could not create search alert: {e.detail}"
