GLOBAL_INSTRUCTIONS = """\
CourtListener MCP server: access to the CourtListener legal research API.

# Data available

The `search` tool covers four primary collections:
- RECAP (federal court filings and dockets from PACER)
- Opinions (case law / court decisions)
- Judges
- Oral arguments (audio recordings of appellate arguments)

For richer detail on individual objects (opinions, dockets, parties, clusters,
courts, etc.) use `get_endpoint_schema` to discover the available REST
endpoint schemas, then `call_endpoint` to fetch from them. These endpoints expose
fields and relationships that the search index does not.

# Use the `fields` argument

Both `search` and `call_endpoint` accept a `fields` argument that restricts
the response payload to the fields you name. CourtListener responses can be
very large; using `fields` aggressively reduces token usage and latency.
Default to requesting only the fields you actually need.

# Opinion text fields

Opinion records carry the full opinion text in several fields, which can be
enormous. Exclude these unless you need the document text. When you do need
the text, prefer the `html_with_citations` field — it consolidates the best
available source (often replacing raw `plain_text`, `html`, `html_lawbox`,
etc.) and includes inline citation markup.

# Linking to dockets and opinions

Docket and opinion URLs on courtlistener.com require *something* after the
ID (normally a case-name slug). Without it, the link 404s. When you don't
have a slug, repeat the resource name as the trailing segment:

    https://www.courtlistener.com/docket/{docket_id}/docket/
    https://www.courtlistener.com/opinion/{opinion_id}/opinion/

This is the safest format — it always resolves correctly even though it
looks redundant.
"""
