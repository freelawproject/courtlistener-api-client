import re

from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from courtlistener.mcp.exceptions import ToolArgumentValidationError
from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.utils import (
    fetch_document_text,
    resolve_cluster_opinion_ids,
)

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

    Input should include exactly one of opinion_id, recap_document_id, or cluster_id.
    """

    name: str = "search_document"
    annotations = ToolAnnotations(
        title="Search Document",
        readOnlyHint=True,
        destructiveHint=False,
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
                "cluster_id": {
                    "type": "integer",
                    "description": (
                        "ID of an opinion cluster (the `cluster_id` in "
                        "search results).  Searches the case's main "
                        "opinion; ids for any concurrences or dissents "
                        "are returned in `sibling_opinion_ids`."
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
            "additionalProperties": False,
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
        result: dict = {"doc_type": doc_type, "doc_id": doc_id, "query": query}

        try:
            text = await fetch_document_text(doc_type, doc_id, client)
        except Exception as exc:
            result["error"] = str(exc)
            return result

        if not text:
            result["error"] = "No text is available for this document."
            return result

        match_count, snippets = self._search_text(text, query, snippet_size)
        result.update(
            {
                "total_chars": len(text),
                "match_count": match_count,
                "shown": len(snippets),
                "snippets": snippets,
            }
        )
        return result

    async def __call__(self, arguments: dict, ctx: Context) -> dict:
        opinion_id = arguments.get("opinion_id")
        recap_document_id = arguments.get("recap_document_id")
        cluster_id = arguments.get("cluster_id")

        provided = [
            value
            for value in (opinion_id, recap_document_id, cluster_id)
            if value is not None
        ]
        if len(provided) != 1:
            raise ToolArgumentValidationError(
                "Provide exactly one of opinion_id, recap_document_id, "
                "or cluster_id.",
                tool_name=self.name,
                argument_names=[
                    "cluster_id",
                    "opinion_id",
                    "recap_document_id",
                ],
            )

        query: str = arguments["query"]
        snippet_size = arguments.get("snippet_size", DEFAULT_SNIPPET_SIZE)

        multi = False
        siblings: list[int] = []

        with self.get_client() as client:
            if cluster_id is not None:
                doc_type = "opinion"
                resolved = resolve_cluster_opinion_ids(cluster_id, client)
                doc_ids = resolved[:1]
                siblings = resolved[1:]
            else:
                if opinion_id is not None:
                    doc_type, raw = "opinion", opinion_id
                else:
                    doc_type, raw = "recap_document", recap_document_id
                multi = isinstance(raw, list)
                doc_ids = raw if isinstance(raw, list) else [raw]

            results = [
                await self._search_one(
                    doc_type, doc_id, query, snippet_size, client
                )
                for doc_id in doc_ids
            ]

        if multi:
            return {"results": results}

        result = results[0]
        if siblings:
            result["sibling_opinion_ids"] = siblings
        return result
