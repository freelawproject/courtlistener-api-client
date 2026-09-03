# Change Log

## Upcoming

The following changes are not yet released, but are code complete:

Features:
- Add `client.prayers` for the Pray and Pay API: `create(recap_document)` and `delete(id)` map to the endpoint's `POST` and `DELETE`; `list()` and `get()` work as on any other endpoint.
- Accept a CourtListener API token as an MCP credential alongside OAuth, so clients that can't run an interactive OAuth flow (server-to-server backends, scripts) can connect. Send it as `Authorization: Token <api_token>`, the same scheme CourtListener's REST API uses. The scheme selects the credential type and is binding: `Bearer` is verified against OIDC userinfo only and `Token` against the CourtListener API.

Changes:
- The client's helper accessors (`alerts`, `docket_alerts`, `prayers`, `citation_lookup`) are now plain attributes set in `__init__` instead of lazy properties with inline imports. The helpers only import the client under `TYPE_CHECKING`, so there was no import cycle to defer around, and constructing them is free.
- The MCP server now uses `AsyncCourtListener` for all tool calls. The sync client inside async tool handlers blocked the worker's event loop, so concurrent tool calls serialized per worker and produced burst client-disconnect noise under load. All tools, the shared tool helpers (`collect_results`, `has_more_results`, `resolve_cluster_opinion_ids`, ...), and the session-store signatures now run on the async client end to end.
- Generate the sync client from the async one: `courtlistener/async_client/` is now the handwritten source of truth, and `courtlistener/sync_client/` is generated from it with unasync by the new `scripts/generate_sync_client.py` script. Like the generated docs and endpoint models, CI regenerates the sync client and fails if the checked-in copy is stale. The generated code is API-identical to the old handwritten sync client, including the deprecated `ResourceIterator` property aliases, which the generator injects since they exist only in the sync flavor.
- Add a PR template with an AI Disclosure section.
- Flatten the generated docs tree: endpoint docs move from `docs/api/endpoints/` to `docs/endpoints/`, MCP tool docs from `docs/mcp/tools/` to `docs/mcp_tools/`, and the cached HTTP OPTIONS dump from `docs/api/http_options.json` to `docs/http_options.json`. The `docs/api/` and `docs/mcp/` folders and their stub READMEs are gone.
- Rename the generator scripts for consistency: `generate_models.py` → `generate_endpoint_models.py`, `update_endpoint_docs.py` → `generate_endpoint_docs.py`, and `update_tool_docs.py` → `generate_mcp_tool_docs.py`.
- Remove `MCP_REQUIRE_OAUTH`. The HTTP server now always authenticates — the auth provider accepts both OAuth bearer tokens and CL API tokens, so an auth-off HTTP mode no longer has a purpose, and the flag's fail-open parsing (any value other than exactly `"true"` silently disabled auth) goes with it. The `Authorization: Token` header pass-through in `MCPTool.get_client` is removed as dead code; stdio mode still resolves its credential from `COURTLISTENER_API_TOKEN`.
- Add `courtlistener/settings.py` with `get_api_base_url()`, now the single source of truth for the CourtListener API root.
- Cache a structured record of each verified token instead of a bare user hash, keyed by credential kind (`mcp:token_info:{kind}:{hmac}`), so an entry verified as one kind can never satisfy a lookup for another. Entries under the old `mcp:token_to_user:` namespace are ignored and re-verified once.
- Token verification degrades to direct verification when the session store is unavailable, instead of turning a Redis blip into a 500 on every request.
- The Redis session backend now treats connection-level failures (DNS blips, dropped connections, timeouts) as cache misses for all session state, not just token verification: reads miss, writes and deletes skip. A blip mid-tool-call now surfaces as a "session may have expired, redo the query" message at worst instead of an unhandled error. Each swallowed failure is logged at error level, so the events still reach Sentry as one grouped issue that escalates during a real outage rather than hiding behind the fallback. With the backend owning that policy, `resolve_token` carries no guards of its own anymore; command-level Redis errors and corrupt cache entries are bugs and raise.
- Add `verify_api_token`, which validates a CourtListener API token against the API root and namespaces it by an HMAC of the token — the same namespace stdio mode already derives.
- Tools that only make CL API calls have been changed to have `openWorldHint=False`.
- Remove `comma_separated_pre_validator`, now redundant as `multiple_choice_validator` already splits on commas and whitespace, and splitting up front broke choice labels containing a comma (`"District Court, D. Alaska"`).

Fix:
- Fix `generate_models.py` dropping `filter_class` 0.
- Fix search's `court` filter mislabeled as `MultipleChoiceFilter` when should be `MultipleChoiceStringFilter`.

### 1.2.0 - 2026-08-04

Features:
- Add support for cluster_id in search_document, read_document, and analyze_citations tools.
- Add support for space or comma-separated values for multiple-choice fields and `fields` field.
- Add support for related fields that don't have a schema.
- Add near-miss suggestions to invalid-choice errors.
- Better response when a model uses `get_choices` tool on a non-choice field.
- Add `AsyncCourtListener` client for asynchronous API operations.

Changes:
- Improve global prompt to clarify that cluster_id is a separate id-space from opinion_id.
- Add terms and privacy policy to index.html.
- Tag `ValidationError` and `ToolArgumentValidationError` errors by model or tool for Sentry.
- Tag `UnauthorizedToolError` errors by tool for Sentry.
- Key upstream CourtListener failures (5xx and transport errors) by status for Sentry, tagged by tool and status.
- Raise `ToolArgumentValidationError` for in-tool argument guards so they share the tool-argument Sentry issue.
- Add `InvalidFieldsError` for invalid `fields` requests, mapped to `ToolArgumentValidationError` in the MCP middleware.
- Add `SessionDataNotFoundError` for stale query/job ids, keyed as its own Sentry issue so spikes surface session-store problems.
- Exempt routine token rotation errors from Sentry.
- Add `idempotentHint` to all MCP tool annotations.
- Move API client to `sync_client` module. All previously top-level names remain importable from `courtlistener`, alongside their async counterparts.
- Deprecate the `ResourceIterator` properties `current_page`, `count`, `document_count`, and `results` in favor of `get_current_page()`, `get_count()`, `get_document_count()`, and `get_results()`. The properties still work but emit a `DeprecationWarning`; the methods have awaitable analogues on `AsyncResourceIterator`.
- Test against Python 3.10 through 3.13 in CI.

Fixes:
- Handle json_schema_extra when it exists but is None.

### 1.1.0 - 2026-07-21

Features:
- Integrate Sentry error reporting in the HTTP MCP server via `sentry-sdk`'s `MCPIntegration`. Configured by the optional `SENTRY_DSN` env var; leaving it unset keeps the SDK in no-op mode so local/dev runs are unaffected.
- Add `search_document` tool for searching for snippets within one or more court opinions or RECAP documents.
- Add generated documentation for API endpoints and MCP tools.
- Add mypy workflow, documentation check, and API check to CI.
- Added in-memory session support for MCP server.

Changes:
- Validate tool arguments against each tool's advertised input schema in `ToolHandlerMiddleware`.
- Add `SentryExemptToolError` for tool errors triaged as known noise, dropped from Sentry reporting via a `before_send` hook.
- Add fallback handling for HTTP errors in MCP tool handler middleware.
- Add error message for rate limit exceeded errors.
- Add `SENTRY_TRACES_SAMPLE_RATE` env var to control the sample rate for Sentry traces.
- Make `search_document` tool always return a dict, even for multi-document searches.
- Add `destructiveHint` to all MCP tool annotations.
- Add OpenAI Apps domain-verification challenge token to MCP server.
- Updated to reflect API changes in CourtListener (7/15/2026).
- Improve endpoint_id and fields arguments and prompts.

Fixes:
- Catch falsy `SENTRY_DSN` variable.
- Fix `endpoint_get_schema` tool to inline refs in the schema.


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

