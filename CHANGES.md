# Change Log

## Upcoming

- Add `CourtListenerAPIError` with parsed response details for more informative error messages.
- Add `SearchAlerts` and `DocketAlerts` helper classes for managing alerts via the API.
- Add `CitationLookup` helper for the citation lookup and verification API.
- Add `num_results` parameter to `search` and `call_endpoint` tools for controlling result count.
- Add `get_more_results` tool for paginating through previous query results.
- Add `dump` and `load` helpers to `ResourceIterator` with iteration index tracking.
- Fix generate endpoints script to handle choice groups.
- Add `get_endpoint_item` tool to MCP server.

## Current

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

