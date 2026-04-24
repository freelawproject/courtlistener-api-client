# CourtListener MCP Server

The **CourtListener MCP server** gives any [Model Context Protocol](https://modelcontextprotocol.io) client — Claude Desktop, Claude.ai, Claude Code, Cursor, and others — access to the CourtListener legal research database. Search U.S. case law, dockets, judges, and oral arguments; extract and verify legal citations; and manage alerts, all from inside your AI client.

The server is hosted by [Free Law Project](https://free.law/), the nonprofit behind CourtListener, at:

```
https://mcp.courtlistener.com/
```

It is the same data that powers [courtlistener.com](https://www.courtlistener.com/): millions of opinions from federal and state courts, the [RECAP archive](https://www.courtlistener.com/recap/) of PACER filings, the [oral arguments collection](https://www.courtlistener.com/audio/), and a comprehensive judges database.

---

## Table of contents

- [What you can do with it](#what-you-can-do-with-it)
- [Requirements](#requirements)
- [Connect a client](#connect-a-client)
  - [Claude.ai and Claude Desktop](#claudeai-and-claude-desktop)
  - [Claude Code](#claude-code)
  - [Other MCP clients](#other-mcp-clients)
- [Authentication](#authentication)
- [Available tools](#available-tools)
- [Usage notes and limits](#usage-notes-and-limits)
- [Troubleshooting](#troubleshooting)
- [Privacy and data handling](#privacy-and-data-handling)
- [Self-hosting / local development](#self-hosting--local-development)
- [Support](#support)

---

## What you can do with it

A few example prompts once the server is connected:

- *"Find Supreme Court opinions about qualified immunity from the last five years."*
- *"Pull every citation out of this brief and tell me which ones are still good law."*
- *"Show me the docket for the SDNY case against Acme Corp. and subscribe me to updates."*
- *"What dissents has Judge Sotomayor written on Fourth Amendment cases?"*
- *"Set up a daily alert for new filings mentioning 'algorithmic discrimination'."*

Under the hood the server exposes a small set of focused tools (search, citation analysis, alert management) plus a generic API-call escape hatch that covers every other CourtListener REST endpoint. See [Available tools](#available-tools).

---

## Requirements

1. **A free CourtListener account.** Sign up at [courtlistener.com/register](https://www.courtlistener.com/register/). Accounts are free for individuals; the [terms of service](https://www.courtlistener.com/terms/) apply.
2. **An MCP-capable client.** Anything that speaks MCP over Streamable HTTP with OAuth 2.0 will work. We test against Claude.ai, Claude Desktop, Claude Code, and Cursor.

You do **not** need a separate API token to use the hosted server. Authentication is handled by signing in with your CourtListener account through your MCP client's OAuth flow.

---

## Connect a client

The server URL for every client is the same:

```
https://mcp.courtlistener.com/
```

### Claude.ai and Claude Desktop

1. Open **Settings → Connectors** (Claude.ai) or **Settings → Connectors** (Claude Desktop).
2. Click **Add custom connector**.
3. Enter:
   - **Name**: `CourtListener`
   - **URL**: `https://mcp.courtlistener.com/`
4. Click **Add**, then **Connect**. A browser window will open for sign-in.
5. Sign in to your CourtListener account and approve the requested permissions (`openid` and `api`).

You're done. Start a new chat and the CourtListener tools will be available.

### Claude Code

```bash
claude mcp add --transport http courtlistener https://mcp.courtlistener.com/
```

The first time you call a CourtListener tool, Claude Code will open a browser window for the OAuth flow. Run `/mcp` inside Claude Code to inspect connection state.

### Other MCP clients

Any client that supports **Streamable HTTP transport** with **OAuth 2.0** can connect. The server publishes [RFC 9728](https://datatracker.ietf.org/doc/html/rfc9728) protected-resource metadata that points clients at CourtListener as the authorization server, so most well-behaved clients can discover everything they need from the URL alone.

For Cursor, Windsurf, and similar editors, look for an "Add MCP server" or "Custom MCP server" option in settings and use the URL above with HTTP transport.

---

## Authentication

The server uses OAuth 2.0 with [Dynamic Client Registration](https://datatracker.ietf.org/doc/html/rfc7591), so individual users do not need to pre-register their MCP client with CourtListener. The flow is standard:

- **Authorization server**: `https://www.courtlistener.com/`
- **Required scopes**: `openid`, `api`
- **Token format**: opaque bearer tokens issued by CourtListener's OIDC provider
- **Verification**: the MCP server validates each token against CourtListener's `/o/userinfo/` endpoint

Tokens are short-lived; clients refresh them automatically. If a token is revoked or expires, the next request returns HTTP 401 with a `WWW-Authenticate` header and the client transparently re-runs the OAuth flow.

The server is a thin proxy: it never stores your CourtListener credentials, and your access token is forwarded directly to the CourtListener REST API on each tool call. If you revoke the connection from your [CourtListener profile](https://www.courtlistener.com/profile/), all access stops immediately.

---

## Available tools

All search and read tools are available to any signed-in user. Alert and subscription tools require a CourtListener account (which you already have if you've signed in).

### Search and retrieval

| Tool | What it does |
| --- | --- |
| `search` | Search case law, dockets, judges, and oral arguments. Supports the same filters as [courtlistener.com/search](https://www.courtlistener.com/help/search/) (jurisdiction, date ranges, judge, citation, etc.). Returns paginated results. |
| `get_endpoint_item` | Fetch a single item (opinion, docket, judge, etc.) by its CourtListener ID. |
| `get_more_results` | Page through additional results from a previous `search` or `call_endpoint` call. |
| `get_counts` | Get the total result count for a previous query (some queries compute counts lazily). |

### Generic API access

For endpoints that don't have a dedicated tool — financial disclosures, opinion clusters, parties, attorneys, citation graphs, and so on — these tools expose the full [CourtListener REST API](https://www.courtlistener.com/help/api/rest/v4/):

| Tool | What it does |
| --- | --- |
| `call_endpoint` | Call any CourtListener API endpoint with custom query parameters. |
| `get_endpoint_schema` | Retrieve the JSON schema (filters, response fields) for a given endpoint. |
| `get_choices` | Look up the valid values for an enum field (e.g. court IDs, case statuses). |

### Citation analysis

| Tool | What it does |
| --- | --- |
| `extract_citations` | Pull legal citations (cases, statutes, *id.*, *supra*, short cites) out of a block of text using [eyecite](https://github.com/freelawproject/eyecite). Runs entirely on the server — no API calls, no rate limits. Great for parsing briefs, opinions, or research notes. |
| `analyze_citations` | Extract citations *and* verify each unique case citation against the CourtListener database. Returns the canonical case name, court, date, and a status (`good`, `bad`, `ambiguous`). Large jobs are batched and return a `job_id` for resumption. |
| `resume_citation_analysis` | Continue verifying remaining citations from an `analyze_citations` job that exceeded the per-call batch limit. |

### Alerts and subscriptions

| Tool | What it does |
| --- | --- |
| `create_search_alert` | Create a [search alert](https://www.courtlistener.com/help/alerts/) with real-time, daily, weekly, or monthly frequency. |
| `delete_search_alert` | Delete a search alert by ID. |
| `subscribe_to_docket_alert` | Subscribe to email updates for a specific docket. |
| `unsubscribe_from_docket_alert` | Unsubscribe from a docket alert. |

These tools modify your CourtListener account state. Your client should prompt you for confirmation before calling them; if it doesn't, you can manage alerts at [courtlistener.com/profile/alerts/](https://www.courtlistener.com/profile/alerts/).

---

## Usage notes and limits

- **Rate limits.** Usage is bounded by CourtListener's API rate limits; see [the API docs](https://www.courtlistener.com/help/api/rest/) for current values. The MCP server itself adds short-lived response caching for read tools to reduce duplicate calls within a session.
- **Result size.** Search and list tools return up to 100 items per call (default 20). Use `get_more_results` to page through larger result sets.
- **Citation analysis batching.** `analyze_citations` verifies up to ~250 unique citations per call to stay under request budgets. Anything larger returns a `job_id`; call `resume_citation_analysis` to continue.
- **Field filtering.** Most read tools accept a `fields` parameter to return only the columns you need, which keeps tool output compact and helps the model focus on what matters.
- **Health check.** `https://mcp.courtlistener.com/health` returns JSON with server status and the deployed Git SHA — useful for incident reports.

---

## Troubleshooting

**The OAuth window won't open / sign-in loops.**
Confirm that your client supports OAuth 2.0 with Dynamic Client Registration. Older versions of some clients only support API-key auth and won't work here. Update to the latest version.

**Tools return "CourtListener rejected the request as unauthorized."**
Your access token was revoked or expired mid-session. The next tool call will surface a clean 401 and your client should refresh automatically. If it doesn't, disconnect and reconnect the server in your client's settings.

**"This app does not have an associated client_id" or similar OAuth errors.**
Your client may have cached stale OAuth metadata. Remove and re-add the connector.

**Search results look wrong or empty.**
The `search` tool maps to the same engine as [courtlistener.com/search](https://www.courtlistener.com/?type=o). Try the same query in the web UI to confirm whether it's a query issue or an MCP issue. The web UI also surfaces helpful hints about syntax and available filters.

**Something else.**
Check `https://mcp.courtlistener.com/health` for server status. If it returns `healthy` but the server is misbehaving, file an issue (see [Support](#support)) with:

- The Git SHA from the `/health` response
- The tool call you made and the error message
- Your MCP client name and version

---

## Privacy and data handling

- **Account data.** The server reads and writes only what's necessary to run the tools you call. Search and read tools are pure proxies; alert tools modify your CourtListener alert preferences.
- **Tokens.** Access tokens are forwarded to CourtListener on each request and cached for up to 10 minutes against an HMAC of the token (the raw token is never stored). When you revoke access from your CourtListener profile, the cache is invalidated on the next request.
- **Session state.** The server stores short-lived per-user state in Redis — pagination cursors and citation-analysis jobs — keyed by an HMAC of the OIDC `sub` claim. This state expires after one hour of inactivity. No tool inputs or outputs are persisted.
- **Logs.** Standard request logs (timestamps, IPs, response codes) are retained for operational debugging and are not used for any other purpose.

For the full data policy that governs the underlying CourtListener service, see the [CourtListener privacy policy](https://www.courtlistener.com/terms/#privacy).

---

## Self-hosting / local development

Most users should use the hosted server at `mcp.courtlistener.com`. If you want to run your own copy — for development, an internal deployment, or a custom configuration — the server ships as part of the `courtlistener-api-client` package on PyPI.

**Quick stdio mode** (easiest, good for trying it out):

```bash
pip install "courtlistener-api-client[mcp]"
export COURTLISTENER_API_TOKEN="your-token"  # from courtlistener.com/profile/api/
courtlistener-mcp
```

Then point your MCP client at the `courtlistener-mcp` command as a stdio server.

**HTTP mode with OAuth** (matches the hosted deployment):

```bash
git clone https://github.com/freelawproject/courtlistener-api-client
cd courtlistener-api-client
docker compose up
```

This launches the MCP server on `http://localhost:8080` with Redis. Required environment variables:

| Variable | Required? | Description |
| --- | --- | --- |
| `REDIS_URL` | yes (HTTP mode) | Redis connection URL for session state. |
| `MCP_SECRET_KEY` | yes (HTTP mode) | Strong random string used as the HMAC key for namespacing user state. |
| `MCP_BASE_URL` | yes (HTTP mode) | Public URL of your MCP deployment (e.g. `https://mcp.example.com`). |
| `MCP_REQUIRE_OAUTH` | no | `true` (default) to require OAuth, `false` to fall back to legacy `Authorization: Token …` headers. |
| `COURTLISTENER_OAUTH_ISSUER` | no | OAuth issuer; defaults to `https://www.courtlistener.com`. |
| `COURTLISTENER_API_BASE_URL` | no | Override for the upstream CourtListener API (useful when pointing at a staging instance). |
| `MCP_TOKEN_CACHE_TTL` | no | Token-to-user-hash cache TTL in seconds; defaults to `600`. |

Source code: [github.com/freelawproject/courtlistener-api-client](https://github.com/freelawproject/courtlistener-api-client)

---

## Support

- **Bug reports and feature requests**: [github.com/freelawproject/courtlistener-api-client/issues](https://github.com/freelawproject/courtlistener-api-client/issues)
- **Security issues**: see [SECURITY.md](SECURITY.md) for responsible disclosure
- **General CourtListener questions**: [free.law/contact/](https://free.law/contact/)
- **Twitter/X**: [@freelawproject](https://twitter.com/freelawproject)

CourtListener and the MCP server are projects of [Free Law Project](https://free.law/), a 501(c)(3) nonprofit. If this server saves you time, please consider [donating](https://free.law/donate/) to keep the underlying data free and open.
