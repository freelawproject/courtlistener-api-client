from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from courtlistener.mcp.tools.mcp_tool import MCPTool


class WithdrawPrayerTool(MCPTool):
    """Withdraw a pending Pray and Pay request for a RECAP document.

    Looks up the user's pending prayer by RECAP document ID and deletes
    it, so you only need the document ID (not the prayer ID). Prayers
    that have already been granted cannot be withdrawn and do not need
    to be: the document is available.

    Use `call_endpoint` with endpoint_id "prayers" to list the user's
    pending prayers.
    """

    name: str = "withdraw_prayer"
    annotations = ToolAnnotations(
        title="Withdraw Prayer",
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=True,
        openWorldHint=True,
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "recap_document_id": {
                    "type": "integer",
                    "description": (
                        "ID of the RECAP document whose prayer to withdraw."
                    ),
                },
            },
            "required": ["recap_document_id"],
            "additionalProperties": False,
        }

    async def __call__(self, arguments: dict, ctx: Context) -> str:
        recap_document_id = arguments["recap_document_id"]

        async with self.get_client() as client:
            prayers = client.prayers.list(recap_document=recap_document_id)
            async for prayer in prayers:
                await client.prayers.delete(prayer["id"])
                return (
                    f"Withdrew prayer for RECAP document {recap_document_id}."
                )
            return (
                f"No pending prayer found for RECAP document "
                f"{recap_document_id}."
            )
