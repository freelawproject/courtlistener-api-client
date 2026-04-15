# Change Log

## Upcoming

The following changes are not yet released, but are code complete:

Features:
- Extract API token from Authorization header for HTTP MCP server.
- Add tool annotation hints to MCP tools.
- Add human-readable titles to all MCP tools via ToolAnnotations.
- Add factory for HTTP MCP server with Redis session state store.
- Add Docker Compose configuration for development.

Changes:
- Update pre-commit hooks to latest versions.
- Refactor MCP server to use FastMCP.

Fixes:
-

### 0.0.6 - 2026-03-19

- A `fields` parameter for `get` methods on resources and for `get_endpoint_item` tool.
- Allow `analyze_citations` tool to pull text from an opinion ID instead of a text string.

### 0.0.5 - 2026-03-18

- Add MCP citation tools: `extract_citations` (local eyecite extraction), `analyze_citations` (extraction + API verification), and `resume_citation_analysis` (session-based resumption for rate-limited verification).
- Add MCP tools for managing alerts: `create_search_alert`, `delete_search_alert`, `subscribe_to_docket_alert`, and `unsubscribe_from_docket_alert`.
- Allow search alerts to accept structured dict queries in addition to raw query strings, with validation via the `SearchEndpoint` model.
- Add `CourtListenerAPIError` with parsed response details for more informative error messages.
- Move MCP server and tools into dedicated `courtlistener.mcp` submodule.
- Add `mcp` optional dependency extra with `eyecite`, `mcp`, and `tiktoken`.
- Add `SearchAlerts` and `DocketAlerts` helper classes for managing alerts via the API.
- Add `CitationLookup` helper for the citation lookup and verification API.
- Add `num_results` parameter to `search` and `call_endpoint` tools for controlling result count.
- Add `get_more_results` tool for paginating through previous query results.
- Add `dump` and `load` helpers to `ResourceIterator` with iteration index tracking.
- Fix generate endpoints script to handle choice groups.
- Add `get_endpoint_item` tool to MCP server.

### 0.0.4 - 2026-03-03

- Add `get_endpoint_schema` and `call_endpoint` tools to MCP server.
- Add `fields` filters to non-search endpoints and add client-side fields filtering to the `search` tool.
- Add `get_choices` tool for long choice lists.
- Add `get_counts` tool for retrieving lazy counts from a previous query.
- Support Python 3.10+
- Fix setuptools package discovery.

## Past

### 0.0.3 - 2026-02-24

- Add API client support for `order_by`.
- Fixes bugs with `search_validator` [#26](https://github.com/freelawproject/courtlistener-api-client/issues/26)
- Adds initial MCP server with `search` tool.

### 0.0.2 - 2026-02-23

- Regenerate endpoints after changes to the API [#6961](https://github.com/freelawproject/courtlistener/issues/6961).

### 0.0.1 - 2026-02-20

- Initial release.

