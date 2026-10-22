"""Out-of-range `chunk_index` in read_document returns a note, not an error."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from courtlistener.mcp.session import InMemorySession, set_session
from courtlistener.mcp.tools import MCP_TOOLS
from courtlistener.mcp.tools.read_document_tool import ReadDocumentTool

TEXT = "a" * 250  # 3 chunks of 100


@pytest.fixture(autouse=True)
def in_memory_session():
    set_session(InMemorySession())
    yield
    set_session(None)


def read(**arguments):
    client = MagicMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False

    async def opinions_get(document_id, fields=None):
        return {"html_with_citations": TEXT}

    client.opinions.get.side_effect = opinions_get
    with patch.object(ReadDocumentTool, "get_client", return_value=client):
        return asyncio.run(
            MCP_TOOLS["read_document"].call(
                {"opinion_id": 1, "chunk_size": 100, **arguments}
            )
        )


class TestOutOfRangeChunks:
    def test_in_range_chunk_has_text_and_no_note(self):
        result = read(chunk_index=2)
        assert result["text"] == "a" * 50
        assert "note" not in result

    def test_single_index_past_end_returns_note(self):
        result = read(chunk_index=5)
        assert "text" not in result
        assert result["total_chunks"] == 3
        assert "chunk_index 5 is past the end" in result["note"]
        assert "(0-2)" in result["note"]

    def test_list_keeps_in_range_chunks(self):
        result = read(chunk_index=[1, 3, 4])
        assert [c["chunk_index"] for c in result["chunks"]] == [1]
        assert result["total_chunks"] == 3
        assert "chunk_index 3, 4 are past the end" in result["note"]

    def test_list_all_past_end_returns_no_chunks(self):
        result = read(chunk_index=[7])
        assert result["chunks"] == []
        assert "note" in result
