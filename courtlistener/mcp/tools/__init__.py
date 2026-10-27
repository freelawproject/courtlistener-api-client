from courtlistener.mcp.tools.analyze_citations_tool import (
    AnalyzeCitationsTool,
)
from courtlistener.mcp.tools.call_endpoint_tool import CallEndpointTool
from courtlistener.mcp.tools.create_search_alert_tool import (
    CreateSearchAlertTool,
)
from courtlistener.mcp.tools.delete_search_alert_tool import (
    DeleteSearchAlertTool,
)
from courtlistener.mcp.tools.extract_citations_tool import (
    ExtractCitationsTool,
)
from courtlistener.mcp.tools.get_api_usage_tool import GetApiUsageTool
from courtlistener.mcp.tools.get_choices_tool import GetChoicesTool
from courtlistener.mcp.tools.get_counts_tool import GetCountsTool
from courtlistener.mcp.tools.get_endpoint_item_tool import GetEndpointItemTool
from courtlistener.mcp.tools.get_endpoint_schema_tool import (
    GetEndpointSchemaTool,
)
from courtlistener.mcp.tools.get_more_results_tool import GetMoreResultsTool
from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.pray_for_document_tool import PrayForDocumentTool
from courtlistener.mcp.tools.read_document_tool import ReadDocumentTool
from courtlistener.mcp.tools.resume_citation_analysis_tool import (
    ResumeCitationAnalysisTool,
)
from courtlistener.mcp.tools.search_document_tool import SearchDocumentTool
from courtlistener.mcp.tools.search_tool import SearchTool
from courtlistener.mcp.tools.subscribe_to_docket_alert_tool import (
    SubscribeToDocketAlertTool,
)
from courtlistener.mcp.tools.unsubscribe_from_docket_alert_tool import (
    UnsubscribeFromDocketAlertTool,
)
from courtlistener.mcp.tools.wiki_list_pages_tool import WikiListPagesTool
from courtlistener.mcp.tools.wiki_read_page_tool import WikiReadPageTool
from courtlistener.mcp.tools.wiki_search_tool import WikiSearchTool
from courtlistener.mcp.tools.withdraw_prayer_tool import WithdrawPrayerTool

MCP_TOOLS: dict[str, MCPTool] = {
    tool.name: tool
    for tool in [
        SearchTool(),
        GetEndpointSchemaTool(),
        CallEndpointTool(),
        GetEndpointItemTool(),
        GetChoicesTool(),
        GetCountsTool(),
        GetMoreResultsTool(),
        ReadDocumentTool(),
        SearchDocumentTool(),
        ExtractCitationsTool(),
        AnalyzeCitationsTool(),
        ResumeCitationAnalysisTool(),
        CreateSearchAlertTool(),
        DeleteSearchAlertTool(),
        SubscribeToDocketAlertTool(),
        UnsubscribeFromDocketAlertTool(),
        PrayForDocumentTool(),
        WithdrawPrayerTool(),
        GetApiUsageTool(),
        WikiListPagesTool(),
        WikiSearchTool(),
        WikiReadPageTool(),
    ]
}
