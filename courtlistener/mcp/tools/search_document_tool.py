import re

from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.utils import fetch_document_text

DEFAULT_SNIPPET_SIZE = 300
MAX_SNIPPETS = 20
MAX_DOCS_PER_CALL = 10


class SearchDocumentTool(MCPTool):
    """Search for snippets within one or more court opinions or RECAP documents.

    Performs a case-insensitive literal search (similar to grep) and
    returns up to 20 matching excerpts per document with surrounding
    context.  Use this to locate specific language—a party name, a
    statutory citation, a key phrase—without reading whole documents.

    Pass a list of IDs (up to 10) to search several
    documents in a single call.  Results are returned as a list; errors
    on individual documents are included as an ``error`` field so one
    unavailable document does not abort the rest.

    When ``match_count`` exceeds ``shown``, the first 20
    matches are returned.  Use ``read_document`` with ``chunk_index`` to
    read the area around a match's ``position`` if you need more context.
    """

    name: str = "search_document"
    annotations = ToolAnnotations(
        title="Search Document",
        readOnlyHint=True,
        openWorldHint=True,
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "opinion_id": {
                    "anyOf": [
                        {"type": "integer"},
                        {
                            "type": "array",
                            "items": {"type": "integer"},
                            "minItems": 1,
                            "maxItems": MAX_DOCS_PER_CALL,
                        },
                    ],
                    "description": (
                        "ID or list of IDs of opinions to search "
                        f"(up to {MAX_DOCS_PER_CALL})."
                    ),
                },
                "recap_document_id": {
                    "anyOf": [
                        {"type": "integer"},
                        {
                            "type": "array",
                            "items": {"type": "integer"},
                            "minItems": 1,
                            "maxItems": MAX_DOCS_PER_CALL,
                        },
                    ],
                    "description": (
                        "ID or list of IDs of RECAP documents to search "
                        f"(up to {MAX_DOCS_PER_CALL})."
                    ),
                },
                "query": {
                    "type": "string",
                    "description": (
                        "Literal phrase to search for (case-insensitive). "
                        f"Up to {MAX_SNIPPETS} matches are returned per document."
                    ),
                },
                "snippet_size": {
                    "type": "integer",
                    "description": (
                        "Characters of context to show on each side of a "
                        f"match (default {DEFAULT_SNIPPET_SIZE})."
                    ),
                    "minimum": 50,
                    "default": DEFAULT_SNIPPET_SIZE,
                },
            },
            "required": ["query"],
        }

    def _search_text(
        self, text: str, query: str, snippet_size: int
    ) -> tuple[int, list[dict]]:
        """Return (match_count, snippets) for a single document text."""
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        matches = list(pattern.finditer(text))
        snippets = []
        for m in matches[:MAX_SNIPPETS]:
            start = max(0, m.start() - snippet_size)
            end = min(len(text), m.end() + snippet_size)
            snippet_text = text[start:end]
            if start > 0:
                snippet_text = "..." + snippet_text
            if end < len(text):
                snippet_text = snippet_text + "..."
            snippets.append({"position": m.start(), "text": snippet_text})
        return len(matches), snippets

    async def _search_one(
        self,
        doc_type: str,
        doc_id: int,
        query: str,
        snippet_size: int,
        client,
    ) -> dict:
        try:
            text = await fetch_document_text(doc_type, doc_id, client)
        except Exception as exc:
            return {
                "doc_type": doc_type,
                "doc_id": doc_id,
                "query": query,
                "error": str(exc),
            }

        if not text:
            return {
                "doc_type": doc_type,
                "doc_id": doc_id,
                "query": query,
                "error": "No text is available for this document.",
            }

        match_count, snippets = self._search_text(text, query, snippet_size)
        return {
            "doc_type": doc_type,
            "doc_id": doc_id,
            "query": query,
            "total_chars": len(text),
            "match_count": match_count,
            "shown": len(snippets),
            "snippets": snippets,
        }

    async def __call__(self, arguments: dict, ctx: Context) -> dict | list:
        opinion_id = arguments.get("opinion_id")
        recap_document_id = arguments.get("recap_document_id")

        if (opinion_id is None) == (recap_document_id is None):
            raise ValueError(
                "Provide exactly one of opinion_id or recap_document_id."
            )

        if opinion_id is not None:
            doc_type = "opinion"
            raw = opinion_id
        else:
            doc_type = "recap_document"
            raw = recap_document_id

        multi = isinstance(raw, list)
        doc_ids: list[int] = raw if multi else [raw]

        query: str = arguments["query"]
        snippet_size = arguments.get("snippet_size", DEFAULT_SNIPPET_SIZE)

        with self.get_client() as client:
            results = [
                await self._search_one(
                    doc_type, doc_id, query, snippet_size, client
                )
                for doc_id in doc_ids
            ]

        return results if multi else results[0]
