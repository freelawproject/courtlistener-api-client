# Change Log

## Upcoming

The following changes are not yet released, but are code complete:

Features:
- Integrate Sentry error reporting in the HTTP MCP server via `sentry-sdk`'s `MCPIntegration`. Configured by the optional `SENTRY_DSN` env var; leaving it unset keeps the SDK in no-op mode so local/dev runs are unaffected.

Changes:
- Add fallback handling for HTTP errors in MCP tool handler middleware.
- Add error message for rate limit exceeded errors.

Fixes:
- Catch falsy `SENTRY_DSN` var.


### 1.0.0 - 2026-05-11

Features:
- Serve MCP server icons (favicon at small sizes, full logo at larger sizes) via the FastMCP `icons` metadata, and expose `/favicon.svg` and `/favicon.ico` routes so Google's favicon service can pick up the logo for the directory listing. Also serve a minimal HTML landing page at `GET /` (the MCP transport itself only handles `POST`/`DELETE`, so methods don't collide) — this gives Googlebot something crawlable and includes explicit `<link rel="icon">` tags pointing at the favicon, which is what Google's favicon cache actually keys off.
- Enable CORS on the HTTP MCP app with `Access-Control-Allow-Origin: *` and the MCP-specific headers (`mcp-protocol-version`, `mcp-session-id`, `Authorization`, `Content-Type`), so browser-based MCP clients (Inspector, Claude.ai OAuth discovery) can complete preflight and send authenticated requests.
- Extract API token from Authorization header for HTTP MCP server.
- Add tool annotation hints to MCP tools.
- Add human-readable titles to all MCP tools via ToolAnnotations.
- Add factory for HTTP MCP server with Redis session state store.
- Add Docker Compose configuration for development.
- Report the image version (Git SHA) on the MCP `/health` endpoint.
- Add gunicorn as an `mcp` optional dependency for running the MCP server in production.
- Add Redis session state store to MCP server.
- Accept OAuth 2.0 bearer tokens in the MCP HTTP transport (gated on
  `MCP_REQUIRE_OAUTH`) and forward them to the CourtListener API as
  `Authorization: Bearer <token>`. Adds an `access_token` parameter
  to `CourtListener` for Bearer auth. Publishes RFC 9728
  protected-resource metadata pointing clients at the CourtListener
  authorization server, but defers token validation itself to CL —
  the MCP is a thin proxy and CL's OAuth2Authentication is the
  authoritative check.

Changes:
- Update pre-commit hooks to latest versions.
- Refactor MCP server to use FastMCP.
- Make COURTLISTENER_API_BASE_URL configurable via environment variable.
- Add CI workflow and Makefile for building and deploying the MCP server.
- Force use of single worker per pod in production.
- Switch MCP server to stateless HTTP. Session-scoped tool state (query pagination, citation analysis jobs) is now stored in Redis under per-user keys derived from an HMAC of the API token, so any worker can serve any request. Adds `MCP_SECRET_KEY` for the HMAC key.
- Verify MCP OAuth tokens against CourtListener's OIDC userinfo endpoint instead of passing them through unchecked, and namespace Redis session state by a stable hash of the resolved `sub` claim rather than the raw access token. Pagination and citation-analysis state now survive access-token rotation, and revoked or invalid tokens produce a proper HTTP 401 with `WWW-Authenticate` so MCP clients re-run OAuth automatically. Downstream 401s from the CourtListener REST API evict the token cache so the next request surfaces the same re-auth signal. Requires the `openid` and `api` scopes, advertised in the protected-resource metadata; adds `MCP_TOKEN_CACHE_TTL` (seconds, default 600) and `COURTLISTENER_OAUTH_USERINFO_URL` for overriding the userinfo endpoint.
- Point index html to the Free Law wiki for MCP setup instructions.
- Add MCP server instructions to the global prompt.
- Add `retry_on_rate_limit` parameter to `citation_lookup` helper for retrying on 429s.

Fixes:
- Fix JSON serialization of dates and datetimes in MCP tools.
- Add valid search types to create search alert tool and client helper.
- Warn in `analyze_citations` output when a verified cluster's case name diverges from the input name, clarify the "occurrences vs unique strings vs unique case clusters" counts in the header, and auto-resolve ambiguous results whose candidate clusters share the same name (surfacing the other cluster IDs).
- Fix `analyze_citations` tool to use the `html_with_citations` field for the opinion text.
- Gracefully error handling for alerts tools.

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

