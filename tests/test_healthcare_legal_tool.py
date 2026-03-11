"""Tests for the HealthcareLegalTool MCP tool."""

from unittest.mock import MagicMock, patch

import pytest

from courtlistener.mcp_tools.healthcare_legal_tool import (
    HEALTHCARE_QUERIES,
    HealthcareLegalTool,
)


@pytest.fixture
def tool():
    return HealthcareLegalTool()


@pytest.fixture
def mock_session():
    return {}


def make_mock_response(results: list, count: int = None):
    """Create a mock CourtListener search response."""
    response = MagicMock()
    response.results = results
    response.current_page = MagicMock()
    response.current_page.count = count or len(results)
    return response


def make_mock_result(
    case_name="Test v. Healthcare Corp",
    date_filed="2023-01-15",
    court_id="ca9",
    citation="123 F.3d 456",
    absolute_url="/opinion/123/test-v-healthcare-corp/",
    snippet="The court found that the employer retaliated...",
):
    return {
        "caseName": case_name,
        "dateFiled": date_filed,
        "court_id": court_id,
        "citation": citation,
        "absolute_url": absolute_url,
        "snippet": snippet,
    }


class TestHealthcareLegalToolSchema:
    def test_name(self, tool):
        assert tool.name == "search_healthcare_legal"

    def test_get_tool_returns_tool(self, tool):
        mcp_tool = tool.get_tool()
        assert mcp_tool.name == "search_healthcare_legal"
        assert mcp_tool.description

    def test_input_schema_has_required_scenario(self, tool):
        schema = tool.get_input_schema()
        assert "scenario" in schema["properties"]
        assert "scenario" in schema["required"]

    def test_input_schema_has_all_scenarios(self, tool):
        schema = tool.get_input_schema()
        enum_values = schema["properties"]["scenario"]["enum"]
        for scenario in HEALTHCARE_QUERIES:
            assert scenario in enum_values

    def test_input_schema_has_optional_fields(self, tool):
        schema = tool.get_input_schema()
        assert "custom_query" in schema["properties"]
        assert "max_results" in schema["properties"]
        assert "order_by" in schema["properties"]


class TestHealthcareLegalToolCall:
    def test_invalid_scenario_returns_error(self, tool, mock_session):
        result = tool({"scenario": "invalid_scenario"}, mock_session)
        text = result.content[0].text
        assert "Unknown scenario" in text
        assert "invalid_scenario" in text

    @patch(
        "courtlistener.mcp_tools.healthcare_legal_tool.HealthcareLegalTool.get_client"
    )
    def test_hipaa_whistleblower_search(
        self, mock_get_client, tool, mock_session
    ):
        mock_client = MagicMock()
        mock_get_client.return_value.__enter__ = MagicMock(
            return_value=mock_client
        )
        mock_get_client.return_value.__exit__ = MagicMock(return_value=False)

        mock_response = make_mock_response(
            results=[make_mock_result(case_name="Nurse v. Regional Hospital")],
            count=42,
        )
        mock_client.search.list.return_value = mock_response

        result = tool({"scenario": "hipaa_whistleblower"}, mock_session)
        text = result.content[0].text

        assert "HEALTHCARE LEGAL SEARCH" in text
        assert "Nurse v. Regional Hospital" in text
        assert "42" in text

        call_kwargs = mock_client.search.list.call_args.kwargs
        assert (
            "HIPAA" in call_kwargs["q"] or "whistleblower" in call_kwargs["q"]
        )
        assert call_kwargs["type"] == "o"
        assert call_kwargs["stat_Precedential"] == "on"

    @patch(
        "courtlistener.mcp_tools.healthcare_legal_tool.HealthcareLegalTool.get_client"
    )
    def test_custom_query_overrides_scenario(
        self, mock_get_client, tool, mock_session
    ):
        mock_client = MagicMock()
        mock_get_client.return_value.__enter__ = MagicMock(
            return_value=mock_client
        )
        mock_get_client.return_value.__exit__ = MagicMock(return_value=False)

        mock_response = make_mock_response(results=[], count=0)
        mock_client.search.list.return_value = mock_response

        tool(
            {
                "scenario": "hipaa_breach",
                "custom_query": "my specific custom query",
            },
            mock_session,
        )

        call_kwargs = mock_client.search.list.call_args.kwargs
        assert call_kwargs["q"] == "my specific custom query"

    @patch(
        "courtlistener.mcp_tools.healthcare_legal_tool.HealthcareLegalTool.get_client"
    )
    def test_max_results_capped_at_100(
        self, mock_get_client, tool, mock_session
    ):
        mock_client = MagicMock()
        mock_get_client.return_value.__enter__ = MagicMock(
            return_value=mock_client
        )
        mock_get_client.return_value.__exit__ = MagicMock(return_value=False)

        mock_response = make_mock_response(results=[], count=0)
        mock_client.search.list.return_value = mock_response

        tool({"scenario": "hipaa_breach", "max_results": 500}, mock_session)

        call_kwargs = mock_client.search.list.call_args.kwargs
        assert call_kwargs["page_size"] == 100

    @patch(
        "courtlistener.mcp_tools.healthcare_legal_tool.HealthcareLegalTool.get_client"
    )
    def test_empty_results_returns_helpful_message(
        self, mock_get_client, tool, mock_session
    ):
        mock_client = MagicMock()
        mock_get_client.return_value.__enter__ = MagicMock(
            return_value=mock_client
        )
        mock_get_client.return_value.__exit__ = MagicMock(return_value=False)

        mock_response = make_mock_response(results=[], count=0)
        mock_client.search.list.return_value = mock_response

        result = tool({"scenario": "hipaa_breach"}, mock_session)
        text = result.content[0].text
        assert "No results found" in text

    def test_all_scenarios_have_queries(self):
        for scenario, config in HEALTHCARE_QUERIES.items():
            assert "query" in config, f"{scenario} missing 'query'"
            assert "type" in config, f"{scenario} missing 'type'"
            assert "description" in config, f"{scenario} missing 'description'"
            assert len(config["query"]) > 0
