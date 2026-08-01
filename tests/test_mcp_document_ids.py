"""Cluster-id vs opinion-id handling in the document tools (issue #208).

Opinion search results identify a case by ``cluster_id``, but the
document tools take opinion ids — separate, overlapping id-spaces.
Passing the search result's id used to silently read whatever opinion
shared that integer.  These tests cover the two mitigations: the
added top-level ``opinion_id`` in search results, and ``cluster_id``
arguments on the tools that take a document id.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastmcp.exceptions import ToolError

from courtlistener.mcp.exceptions import ToolArgumentValidationError
from courtlistener.mcp.session import InMemorySession, get_session, set_session
from courtlistener.mcp.tools import MCP_TOOLS
from courtlistener.mcp.tools.analyze_citations_tool import AnalyzeCitationsTool
from courtlistener.mcp.tools.get_more_results_tool import GetMoreResultsTool
from courtlistener.mcp.tools.read_document_tool import ReadDocumentTool
from courtlistener.mcp.tools.search_document_tool import SearchDocumentTool
from courtlistener.mcp.tools.search_tool import SearchTool
from courtlistener.mcp.tools.utils import (
    add_opinion_ids,
    resolve_cluster_opinion_ids,
)


class FakeIterator:
    """The slice of the ResourceIterator interface the tools consume."""

    def __init__(self, results):
        self._results = list(results)
        self.current_page = SimpleNamespace(
            results=self._results, count=len(self._results)
        )
        self._page_result_index = len(self._results)

    def get_current_page(self):
        return self.current_page

    def __iter__(self):
        return iter(self._results)

    def has_next(self):
        return False

    def dump(self):
        return {}


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def in_memory_session():
    set_session(InMemorySession())
    yield
    set_session(None)


def make_client(
    opinion_texts: dict[int, str] | None = None,
    cluster_opinions: dict[int, list[int] | list[dict]] | None = None,
):
    """A client mock serving the fetches the document tools perform.

    ``cluster_opinions`` maps a cluster id to its opinions, given either
    as bare ids or as dicts when a test cares about ``type`` order.
    """
    client = MagicMock()
    client.__enter__.return_value = client
    client.__exit__.return_value = False

    def opinions_get(doc_id, fields=None):
        return {"html_with_citations": (opinion_texts or {}).get(doc_id, "")}

    def opinions_list(cluster=None, fields=None):
        opinions = (cluster_opinions or {}).get(cluster, [])
        return FakeIterator(
            [
                opinion if isinstance(opinion, dict) else {"id": opinion}
                for opinion in opinions
            ]
        )

    client.opinions.get.side_effect = opinions_get
    client.opinions.list.side_effect = opinions_list
    return client


class TestAddOpinionIds:
    def test_adds_the_nested_opinion_id(self):
        results = [{"cluster_id": 8695893, "opinions": [{"id": 8678997}]}]
        add_opinion_ids(results)
        assert results[0]["opinion_id"] == 8678997

    def test_picks_the_main_opinion_not_the_first_listed(self):
        """Citizens United as `search` really returns it: the nested
        opinions come back in relevance order, so entry [0] is Stevens'
        partial dissent and the majority sits fourth.  Search spells the
        types differently from the REST API, so both must rank."""
        results = [
            {
                "cluster_id": 1741,
                "opinions": [
                    {
                        "id": 9413190,
                        "type": "in-part-opinion",
                        "ordering_key": 4,
                    },
                    {
                        "id": 1741,
                        "type": "combined-opinion",
                        "ordering_key": None,
                    },
                    {
                        "id": 9413191,
                        "type": "in-part-opinion",
                        "ordering_key": 5,
                    },
                    {
                        "id": 9413187,
                        "type": "lead-opinion",
                        "ordering_key": 1,
                    },
                ],
            }
        ]
        add_opinion_ids(results)
        assert results[0]["opinion_id"] == 9413187

    def test_search_type_spellings_rank_when_unordered(self):
        """With no ordering_key anywhere, search's own type labels
        still have to identify the majority."""
        results = [
            {
                "opinions": [
                    {"id": 10, "type": "dissent", "ordering_key": None},
                    {"id": 11, "type": "lead-opinion", "ordering_key": None},
                ]
            }
        ]
        add_opinion_ids(results)
        assert results[0]["opinion_id"] == 11

    def test_leaves_results_without_opinions_untouched(self):
        results = [{"docket_id": 1}, {"opinions": []}, {"opinions": None}]
        add_opinion_ids(results)
        assert all("opinion_id" not in r for r in results)

    def test_does_not_clobber_existing_opinion_id(self):
        results = [{"opinion_id": 1, "opinions": [{"id": 2}]}]
        add_opinion_ids(results)
        assert results[0]["opinion_id"] == 1

    def test_search_tool_adds_id_and_fields_filtering_keeps_it(self):
        """The added id must survive `fields` — the recommended usage."""
        tool = SearchTool()
        client = make_client()
        client.api_token = "test-token"
        client.search.list.return_value = FakeIterator(
            [
                {
                    "caseName": "NYSA Series Trust v. Dessein",
                    "cluster_id": 8695893,
                    "opinions": [{"id": 8678997}],
                }
            ]
        )
        with patch.object(SearchTool, "get_client", return_value=client):
            result = run(tool({"type": "o", "fields": ["caseName"]}, None))
        assert result["results"] == [
            {
                "caseName": "NYSA Series Trust v. Dessein",
                "opinion_id": 8678997,
            }
        ]
        assert "missing_fields" not in result

    def test_get_more_results_adds_opinion_id(self):
        tool = GetMoreResultsTool()
        client = make_client()
        client.api_token = "test-token"
        run(get_session().store_query("qid12345", {"response": {}}, client))
        fake = FakeIterator([{"cluster_id": 1, "opinions": [{"id": 42}]}])
        fake._page_result_index = 0  # unconsumed results remain
        with (
            patch.object(
                GetMoreResultsTool, "get_client", return_value=client
            ),
            patch(
                "courtlistener.mcp.tools.get_more_results_tool."
                "ResourceIterator"
            ) as iterator_cls,
        ):
            iterator_cls.load.return_value = fake
            result = run(tool({"query_id": "qid12345"}, None))
        assert result["results"][0]["opinion_id"] == 42


class TestResolveClusterOpinionIds:
    def test_returns_the_cluster_s_opinion_ids(self):
        client = make_client(cluster_opinions={8695893: [8678997, 8678998]})
        assert resolve_cluster_opinion_ids(8695893, client) == [
            8678997,
            8678998,
        ]

    def test_empty_cluster_raises(self):
        client = make_client(cluster_opinions={})
        with pytest.raises(ValueError, match="no opinions"):
            resolve_cluster_opinion_ids(123, client)

    def test_ordering_key_decides(self):
        """Citizens United (cluster 1741) as the API really returns it:
        highest ordering_key first, so the last partial dissent leads
        and the legacy combined opinion carries no key at all."""
        client = make_client(
            cluster_opinions={
                1741: [
                    {
                        "id": 9413191,
                        "type": "035concurrenceinpart",
                        "ordering_key": 5,
                    },
                    {
                        "id": 9413190,
                        "type": "035concurrenceinpart",
                        "ordering_key": 4,
                    },
                    {
                        "id": 9413189,
                        "type": "030concurrence",
                        "ordering_key": 3,
                    },
                    {
                        "id": 9413188,
                        "type": "030concurrence",
                        "ordering_key": 2,
                    },
                    {"id": 9413187, "type": "020lead", "ordering_key": 1},
                    {"id": 1741, "type": "010combined", "ordering_key": None},
                ]
            }
        )
        assert resolve_cluster_opinion_ids(1741, client) == [
            9413187,  # Kennedy's majority, ordering_key 1
            9413188,
            9413189,
            9413190,
            9413191,
            1741,  # no ordering_key, so last
        ]

    def test_type_breaks_ties_when_ordering_key_is_absent(self):
        """Older imported clusters carry no ordering_key at all."""
        client = make_client(
            cluster_opinions={
                5: [
                    {"id": 10, "type": "040dissent", "ordering_key": None},
                    {"id": 11, "type": "030concurrence", "ordering_key": None},
                    {"id": 12, "type": "020lead", "ordering_key": None},
                ]
            }
        )
        assert resolve_cluster_opinion_ids(5, client)[0] == 12

    def test_untyped_opinions_keep_a_stable_order(self):
        client = make_client(cluster_opinions={5: [12, 10, 11]})
        assert resolve_cluster_opinion_ids(5, client) == [10, 11, 12]

    def test_requests_only_the_fields_it_sorts_on(self):
        client = make_client(cluster_opinions={5: [10]})
        resolve_cluster_opinion_ids(5, client)
        client.opinions.list.assert_called_once_with(
            cluster=5, fields=["id", "type", "ordering_key"]
        )


class TestReadDocumentClusterId:
    def test_cluster_id_resolves_to_the_main_opinion(self):
        tool = ReadDocumentTool()
        client = make_client(
            opinion_texts={8678997: "securities text"},
            cluster_opinions={8695893: [8678997, 9000001]},
        )
        with patch.object(ReadDocumentTool, "get_client", return_value=client):
            result = run(tool({"cluster_id": 8695893}, None))
        assert result["doc_id"] == 8678997
        assert result["sibling_opinion_ids"] == [9000001]
        assert result["text"] == "securities text"

    def test_rejects_multiple_id_kinds(self):
        with pytest.raises(ToolArgumentValidationError, match="exactly one"):
            run(ReadDocumentTool()({"opinion_id": 1, "cluster_id": 2}, None))

    def test_schema_accepts_cluster_id(self):
        MCP_TOOLS["read_document"].validate_arguments({"cluster_id": 123})

    def test_fetch_failure_in_cluster_mode_keeps_siblings(self):
        tool = ReadDocumentTool()
        client = make_client(cluster_opinions={5: [10, 11]})
        client.opinions.get.side_effect = RuntimeError("HTTP 404: not found")
        with patch.object(ReadDocumentTool, "get_client", return_value=client):
            result = run(tool({"cluster_id": 5}, None))
        assert result["doc_id"] == 10
        assert result["error"] == "HTTP 404: not found"
        assert result["sibling_opinion_ids"] == [11]


class TestSearchDocumentClusterId:
    def test_searches_only_the_main_opinion(self):
        """One cluster costs one search, not one per opinion — a
        fan-out would exhaust a free-tier rate limit in a single call
        and has no way to resume."""
        tool = SearchDocumentTool()
        client = make_client(
            opinion_texts={10: "alpha beta", 11: "gamma alpha"},
            cluster_opinions={5: [10, 11]},
        )
        with patch.object(
            SearchDocumentTool, "get_client", return_value=client
        ):
            result = run(tool({"cluster_id": 5, "query": "alpha"}, None))
        assert result["doc_id"] == 10
        assert result["match_count"] == 1
        assert result["sibling_opinion_ids"] == [11]
        assert "results" not in result  # single result, not a list

    def test_single_opinion_cluster_reports_no_siblings(self):
        tool = SearchDocumentTool()
        client = make_client(
            opinion_texts={10: "alpha"},
            cluster_opinions={5: [10]},
        )
        with patch.object(
            SearchDocumentTool, "get_client", return_value=client
        ):
            result = run(tool({"cluster_id": 5, "query": "alpha"}, None))
        assert result["doc_id"] == 10
        assert "sibling_opinion_ids" not in result

    def test_empty_cluster_raises(self):
        tool = SearchDocumentTool()
        client = make_client(cluster_opinions={})
        with (
            patch.object(
                SearchDocumentTool, "get_client", return_value=client
            ),
            pytest.raises(ValueError, match="no opinions"),
        ):
            run(tool({"cluster_id": 7, "query": "x"}, None))

    def test_schema_accepts_cluster_id(self):
        MCP_TOOLS["search_document"].validate_arguments(
            {"cluster_id": 1, "query": "x"}
        )

    def test_schema_rejects_cluster_id_list(self):
        """Multiple documents go through opinion_id, which is bounded."""
        with pytest.raises(ToolError):
            MCP_TOOLS["search_document"].validate_arguments(
                {"cluster_id": [1, 2], "query": "x"}
            )

    def test_opinion_id_list_still_searches_each(self):
        tool = SearchDocumentTool()
        client = make_client(opinion_texts={10: "alpha", 11: "alpha"})
        with patch.object(
            SearchDocumentTool, "get_client", return_value=client
        ):
            result = run(
                tool({"opinion_id": [10, 11], "query": "alpha"}, None)
            )
        assert [r["doc_id"] for r in result["results"]] == [10, 11]

    def test_rejects_multiple_id_kinds(self):
        with pytest.raises(ToolArgumentValidationError, match="exactly one"):
            run(
                SearchDocumentTool()(
                    {"opinion_id": 1, "cluster_id": 2, "query": "x"}, None
                )
            )


class TestAnalyzeCitationsClusterId:
    def test_no_text_error_mentions_cluster_id(self):
        tool = AnalyzeCitationsTool()
        client = make_client()  # no opinion_texts: html_with_citations empty
        with (
            patch.object(
                AnalyzeCitationsTool, "get_client", return_value=client
            ),
            pytest.raises(ValueError, match="cluster_id"),
        ):
            run(tool({"opinion_id": 1}, None))

    def test_schema_accepts_cluster_id(self):
        MCP_TOOLS["analyze_citations"].validate_arguments({"cluster_id": 123})

    def test_rejects_multiple_id_kinds(self):
        with pytest.raises(ToolArgumentValidationError, match="exactly one"):
            run(
                AnalyzeCitationsTool()(
                    {"opinion_id": 1, "cluster_id": 2}, None
                )
            )

    def test_cluster_id_analyzes_the_main_opinion(self):
        """A cluster id must reach the cluster's opinion, not the
        unrelated opinion that happens to share the integer."""
        tool = AnalyzeCitationsTool()
        client = make_client(
            opinion_texts={10: "no citations here"},
            cluster_opinions={5: [10, 11]},
        )
        with patch.object(
            AnalyzeCitationsTool, "get_client", return_value=client
        ):
            output = run(tool({"cluster_id": 5}, None))
        client.opinions.get.assert_called_once_with(10)
        assert "the main opinion of 2 in cluster 5" in output
        assert "opinion_id: 11" in output
        assert "No citations found." in output

    def test_single_opinion_cluster_adds_no_note(self):
        tool = AnalyzeCitationsTool()
        client = make_client(
            opinion_texts={10: "no citations here"},
            cluster_opinions={5: [10]},
        )
        with patch.object(
            AnalyzeCitationsTool, "get_client", return_value=client
        ):
            output = run(tool({"cluster_id": 5}, None))
        assert output == "No citations found."

    def test_empty_cluster_raises(self):
        tool = AnalyzeCitationsTool()
        client = make_client(cluster_opinions={})
        with (
            patch.object(
                AnalyzeCitationsTool, "get_client", return_value=client
            ),
            pytest.raises(ValueError, match="no opinions"),
        ):
            run(tool({"cluster_id": 5}, None))
