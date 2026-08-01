import math

from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from courtlistener.mcp.exceptions import ToolArgumentValidationError
from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.utils import (
    fetch_document_text,
    resolve_cluster_opinion_ids,
)

DEFAULT_CHUNK_SIZE = 8000
MAX_CHUNKS_PER_CALL = 10


class ReadDocumentTool(MCPTool):
    """Read the full text of a court opinion or RECAP document.

    Fetches the document text and either returns it in full or as one or
    more paginated chunks.  For opinions, uses the ``html_with_citations``
    field (the most complete text representation).  For RECAP documents,
    uses ``plain_text``.

    **Usage patterns**

    - *Full read*: omit ``chunk_index`` to receive the entire document
      along with its ``total_chars``.
    - *Single chunk*: pass an integer ``chunk_index`` (0-based) to
      receive one window of ``chunk_size`` characters.  The response
      includes ``total_chunks`` so you can jump directly to any part of
      the document (e.g. set ``chunk_index`` to ``total_chunks - 1`` to
      read the conclusion).
    - *Multiple chunks*: pass a list of chunk indexes to retrieve several
      non-contiguous windows in a single call (up to
      10).  Useful when you already know the chunk
      size from a previous call and want the next N pages at once.

    Input should include exactly one of opinion_id, recap_document_id, or cluster_id.
    """

    name: str = "read_document"
    annotations = ToolAnnotations(
        title="Read Document",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "opinion_id": {
                    "type": "integer",
                    "description": "ID of the opinion to read.",
                },
                "recap_document_id": {
                    "type": "integer",
                    "description": "ID of the RECAP document to read.",
                },
                "cluster_id": {
                    "type": "integer",
                    "description": (
                        "ID of an opinion cluster (the `cluster_id` in "
                        "search results).  Reads the case's main "
                        "opinion; ids for any concurrences or dissents "
                        "are returned in `sibling_opinion_ids`."
                    ),
                },
                "chunk_index": {
                    "anyOf": [
                        {"type": "integer", "minimum": 0},
                        {
                            "type": "array",
                            "items": {"type": "integer", "minimum": 0},
                            "minItems": 1,
                            "maxItems": MAX_CHUNKS_PER_CALL,
                        },
                    ],
                    "description": (
                        "0-based index (or list of indexes) of the chunk(s) "
                        "to return.  Omit to receive the full document text."
                    ),
                },
                "chunk_size": {
                    "type": "integer",
                    "description": (
                        f"Characters per chunk (default {DEFAULT_CHUNK_SIZE}). "
                        "Only relevant when chunk_index is supplied."
                    ),
                    "minimum": 100,
                    "default": DEFAULT_CHUNK_SIZE,
                },
            },
            "additionalProperties": False,
        }

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

        chunk_index = arguments.get("chunk_index")
        chunk_size = arguments.get("chunk_size", DEFAULT_CHUNK_SIZE)

        siblings: list[int] = []
        with self.get_client() as client:
            if cluster_id is not None:
                resolved = resolve_cluster_opinion_ids(cluster_id, client)
                doc_type, doc_id = "opinion", resolved[0]
                siblings = resolved[1:]
            elif opinion_id is not None:
                doc_type, doc_id = "opinion", opinion_id
            else:
                assert recap_document_id is not None  # for mypy
                doc_type, doc_id = "recap_document", recap_document_id

            try:
                text = await fetch_document_text(doc_type, doc_id, client)
            except Exception as exc:
                # In cluster mode the resolution already succeeded, so
                # keep the sibling ids usable instead of losing them to
                # a bare error on the first opinion.
                if cluster_id is None:
                    raise
                failure: dict = {
                    "doc_type": doc_type,
                    "doc_id": doc_id,
                    "error": str(exc),
                }
                if siblings:
                    failure["sibling_opinion_ids"] = siblings
                return failure

        result: dict = {"doc_type": doc_type, "doc_id": doc_id}
        if siblings:
            result["sibling_opinion_ids"] = siblings

        if not text:
            result["error"] = "No text is available for this document."
            return result

        total_chars = len(text)
        total_chunks = math.ceil(total_chars / chunk_size)

        result["total_chars"] = total_chars

        if chunk_index is None:
            result["text"] = text
        elif isinstance(chunk_index, list):
            out_of_range = [i for i in chunk_index if i >= total_chunks]
            if out_of_range:
                raise ToolArgumentValidationError(
                    f"chunk_index value(s) {out_of_range} are out of range; "
                    f"document has {total_chunks} chunk(s) of "
                    f"{chunk_size} characters each.",
                    tool_name=self.name,
                    argument_names=["chunk_index"],
                )
            result["chunk_size"] = chunk_size
            result["total_chunks"] = total_chunks
            result["chunks"] = [
                {
                    "chunk_index": i,
                    "text": text[i * chunk_size : (i + 1) * chunk_size],
                }
                for i in chunk_index
            ]
        else:
            if chunk_index >= total_chunks:
                raise ToolArgumentValidationError(
                    f"chunk_index {chunk_index} is out of range; "
                    f"document has {total_chunks} chunk(s) of "
                    f"{chunk_size} characters each.",
                    tool_name=self.name,
                    argument_names=["chunk_index"],
                )
            start = chunk_index * chunk_size
            result["chunk_index"] = chunk_index
            result["chunk_size"] = chunk_size
            result["total_chunks"] = total_chunks
            result["text"] = text[start : start + chunk_size]

        return result
