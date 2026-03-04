# Change Log

## Upcoming

The following changes are not yet released, but are code complete:

Features:
- A new workflow monitors PyPi for malicious packages. Incredibly we already have one. This will run nightly to see if any others pop up.

Changes:
-

Fixes:
- 

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

