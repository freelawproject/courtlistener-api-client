import json

from mcp.types import CallToolResult, TextContent, ToolAnnotations

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.tools.mcp_tool import MCPTool


class CreateSearchAlertTool(MCPTool):
    """Create a search alert on CourtListener.

    Use `call_endpoint` with endpoint_id "alerts" to list existing alerts.
    """

    name: str = "create_search_alert"
    annotations = ToolAnnotations(
        title="Creating Search Alert",
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
                    "enum": ["d", "r"],
                    "description": (
                        'Optional alert type: "d" (docket) or "r" (recap).'
                    ),
                },
            },
            "required": ["name", "query", "rate"],
        }

    def __call__(self, arguments: dict, session: dict) -> CallToolResult:
        name = arguments["name"]
        query = arguments["query"]
        rate = arguments["rate"]
        alert_type = arguments.get("alert_type")

        try:
            with self.get_client() as client:
                alert = client.alerts.create(
                    name=name,
                    query=query,
                    rate=rate,
                    alert_type=alert_type,
                )
                return CallToolResult(
                    content=[
                        TextContent(
                            type="text",
                            text=json.dumps(alert, indent=2),
                        )
                    ]
                )
        except (CourtListenerAPIError, ValueError, TypeError) as exc:
            return CallToolResult(
                content=[TextContent(type="text", text=str(exc))],
                isError=True,
            )
