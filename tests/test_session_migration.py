"""Tests for the SessionStore migration: string IDs, utils, schemas."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from courtlistener.mcp.session import InMemorySessionStore
from courtlistener.mcp.tools.get_counts_tool import GetCountsTool
from courtlistener.mcp.tools.get_more_results_tool import GetMoreResultsTool
from courtlistener.mcp.tools.resume_citation_analysis_tool import (
    ResumeCitationAnalysisTool,
)
from courtlistener.mcp.tools.utils import prepare_query_id


class TestPrepareQueryId:
    def test_returns_string(self):
        """prepare_query_id must return an 8-char hex string."""
        session = InMemorySessionStore()
        mock_response = MagicMock()
        mock_response.dump.return_value = {}

        query_id = prepare_query_id(mock_response, session, "user1")
        assert isinstance(query_id, str)
        assert len(query_id) == 8

    def test_stores_via_session_store(self):
        """prepare_query_id must store data via session.store_query."""
        session = InMemorySessionStore()
        mock_response = MagicMock()
        mock_response.dump.return_value = {"next": "http://example.com"}

        with patch.object(session, "make_id", return_value="abc12345"):
            query_id = prepare_query_id(mock_response, session, "user1")

        assert query_id == "abc12345"
        stored = session.get_query("user1", "abc12345")
        assert stored is not None
        assert stored["response"] == {"next": "http://example.com"}

    def test_stores_fields_when_provided(self):
        """prepare_query_id should include fields in stored data."""
        session = InMemorySessionStore()
        mock_response = MagicMock()
        mock_response.dump.return_value = {}

        with patch.object(session, "make_id", return_value="abc12345"):
            prepare_query_id(
                mock_response, session, "user1", fields=["id", "name"]
            )

        stored = session.get_query("user1", "abc12345")
        assert stored["fields"] == ["id", "name"]

    def test_omits_fields_key_when_none(self):
        """prepare_query_id must not store 'fields' key when None."""
        session = InMemorySessionStore()
        mock_response = MagicMock()
        mock_response.dump.return_value = {}

        with patch.object(session, "make_id", return_value="abc12345"):
            prepare_query_id(mock_response, session, "user1", fields=None)

        stored = session.get_query("user1", "abc12345")
        assert "fields" not in stored

    def test_user_isolation(self):
        """Queries from different users must not interfere."""
        session = InMemorySessionStore()
        mock_response = MagicMock()
        mock_response.dump.return_value = {"data": "x"}

        ids = iter(["aaaa0001", "bbbb0002"])
        with patch.object(session, "make_id", side_effect=ids):
            id_a = prepare_query_id(mock_response, session, "alice")
            id_b = prepare_query_id(mock_response, session, "bob")

        # Each user has their own entry; the other user cannot see it
        assert session.get_query("alice", id_a) is not None
        assert session.get_query("bob", id_b) is not None
        assert session.get_query("alice", id_b) is None
        assert session.get_query("bob", id_a) is None


class TestIdSchemaTypes:
    def test_get_more_results_query_id_is_string(self):
        """get_more_results must declare query_id as string type."""
        tool = GetMoreResultsTool()
        schema = tool.get_input_schema()
        assert schema["properties"]["query_id"]["type"] == "string"

    def test_get_counts_query_id_is_string(self):
        """get_counts must declare query_id as string type."""
        tool = GetCountsTool()
        schema = tool.get_input_schema()
        assert schema["properties"]["query_id"]["type"] == "string"

    def test_resume_citation_analysis_job_id_is_string(self):
        """resume_citation_analysis must declare job_id as string type."""
        tool = ResumeCitationAnalysisTool()
        schema = tool.get_input_schema()
        assert schema["properties"]["job_id"]["type"] == "string"


class TestErrorHandling:
    def test_get_counts_missing_query_returns_error(self):
        """get_counts returns isError when query_id not in session."""
        tool = GetCountsTool()
        session = InMemorySessionStore()
        result = tool({"query_id": "nonexistent"}, session)
        assert result.isError
        assert "not found" in result.content[0].text.lower()

    def test_get_more_results_missing_query_returns_error(self):
        """get_more_results returns isError when query_id not in session."""
        tool = GetMoreResultsTool()
        session = InMemorySessionStore()
        result = tool({"query_id": "nonexistent"}, session)
        assert result.isError
        assert "not found" in result.content[0].text.lower()

    def test_resume_missing_job_returns_error(self):
        """resume_citation_analysis returns isError when job not found."""
        tool = ResumeCitationAnalysisTool()
        session = InMemorySessionStore()
        result = tool({"job_id": "nonexistent"}, session)
        assert result.isError
        assert "not found" in result.content[0].text.lower()
