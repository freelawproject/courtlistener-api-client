from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from courtlistener.exceptions import CourtListenerAPIError
from courtlistener.mcp.tools.mcp_tool import MCPTool

DOCUMENT_FIELDS = ["id", "is_available", "document_number", "description"]


class PrayForDocumentTool(MCPTool):
    """Request a RECAP document that is not yet available on CourtListener
    through Pray and Pay.

    Prayers are pooled across users: when anyone buys the document from
    PACER, it is added to CourtListener for free and everyone praying for
    it is emailed. Nothing is charged to the user, but fulfillment is not
    immediate and not guaranteed.

    Only documents whose `is_available` is false need a prayer. This tool
    checks first and, if the document is already available, tells you to
    read it with `read_document` instead. Prayers count against a daily
    per-user limit, so only pray when the user actually wants the filing.

    Use `call_endpoint` with endpoint_id "prayers" to list the user's
    pending prayers.
    """

    name: str = "pray_for_document"
    annotations = ToolAnnotations(
        title="Pray for Document",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "recap_document_id": {
                    "type": "integer",
                    "description": (
                        "ID of the RECAP document to pray for (the `id` of "
                        "a `recap_documents` record, not a docket entry or "
                        "docket ID)."
                    ),
                },
            },
            "required": ["recap_document_id"],
            "additionalProperties": False,
        }

    async def __call__(self, arguments: dict, ctx: Context) -> dict | str:
        recap_document_id = arguments["recap_document_id"]

        async with self.get_client() as client:
            try:
                document = await client.recap_documents.get(
                    recap_document_id, fields=DOCUMENT_FIELDS
                )
            except CourtListenerAPIError as e:
                if e.status_code == 404:
                    return (
                        f"No RECAP document found with id {recap_document_id}."
                    )
                raise

            if document.get("is_available"):
                return (
                    f"RECAP document {recap_document_id} is already "
                    "available on CourtListener, so no prayer is needed. "
                    "Use `read_document` with "
                    f"recap_document_id={recap_document_id} to read it."
                )

            try:
                prayer = await client.prayers.create(recap_document_id)
            except CourtListenerAPIError as e:
                if e.status_code != 400:
                    raise
                if "unique set" in str(e.detail):
                    return (
                        f"You are already praying for RECAP document "
                        f"{recap_document_id}. You will be emailed when it "
                        "becomes available."
                    )
                return (
                    f"Could not pray for RECAP document {recap_document_id}: "
                    f"{e.detail}"
                )

            return {
                **prayer,
                "document_number": document.get("document_number"),
                "description": document.get("description"),
                "message": (
                    "Prayer recorded. When another user buys this document "
                    "from PACER it will be added to CourtListener for free "
                    "and you will be emailed. This can take days or never "
                    "happen; check back with `read_document` later."
                ),
            }
