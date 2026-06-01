GLOBAL_INSTRUCTIONS = """\
CourtListener MCP server: access to the CourtListener legal research API.

# Data available

The `search` tool covers four primary collections:
- RECAP (federal court cases/dockets, filings, parties, and attorneys from PACER)
- Opinions (case law / court decisions)
- Judges (their financial disclosures are not searchable, but are available via the regular API)
- Oral arguments (audio recordings and transcripts of appellate arguments)

For richer detail on individual objects (opinions, dockets, parties, clusters,
courts, etc.) use `get_endpoint_schema` to discover the available REST
endpoint schemas, then `call_endpoint` to fetch from them. These endpoints expose
fields and relationships that the search index does not.

# Use the `fields` argument

Both `search` and `call_endpoint` accept a `fields` argument that restricts
the response payload to the fields you name. CourtListener responses can be
very large; using `fields` aggressively reduces token usage and latency.
Default to requesting only the fields you actually need.

# Reading document text

To read the text of an opinion or RECAP document, use the dedicated
`read_document` and `search_document` tools rather than fetching raw text
fields from the endpoints directly. These tools cache documents across users,
support paginated reading by character chunk, and let you grep for snippets
without loading the whole document. For opinions, they use the
`html_with_citations` field (the most reliable text source, with inline
citation markup); for RECAP documents, they use `plain_text`.

When fetching opinion or RECAP document records via `call_endpoint` or
`get_endpoint_item`, exclude text fields (`html_with_citations`, `plain_text`,
`html`, `html_lawbox`, etc.) from the `fields` argument — they can be
enormous and are better accessed through `read_document`.

Avoid trying to fetch PDFs directly, as the courtlistener storages urls are not
fetchable for AI agents.

# Linking to dockets and opinions

Docket and opinion URLs on courtlistener.com require *something* after the
ID (normally a case-name slug). Without it, the link 404s. When you don't
have a slug, repeat the resource name as the trailing segment:

    https://www.courtlistener.com/docket/{docket_id}/docket/
    https://www.courtlistener.com/opinion/{opinion_id}/opinion/

This is the safest format — it always resolves correctly even though it
looks redundant.
"""
