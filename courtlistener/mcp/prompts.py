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

CourtListener responses can be very large; restricting the fields returned
aggressively reduces token usage and latency. Default to requesting only the
fields you actually need.

Where `fields` goes depends on the tool:
- `search` and `get_endpoint_item` take `fields` as a top-level argument.
- `call_endpoint` takes it inside `query`, along with every other endpoint
  parameter — it has no top-level `fields` argument. For example:
  `{"endpoint_id": "dockets", "query": {"court": "scotus", "fields": ["id", "case_name"]}}`

The difference is not arbitrary. The non-search endpoints support `fields`
natively, so it belongs in `query` with their other parameters and
CourtListener does the filtering. Search does not support it, so the `search`
tool accepts `fields` itself and filters after the fact.

# Field names differ between search and the API

Field names in `search` results are not the API field names used by
`call_endpoint` and `get_endpoint_item`. Search returns camelCase names like
`caseName`, `dateFiled`, and `citation`; the corresponding API fields are
`case_name`, `date_filed`, and `citations` (note the plural). Don't copy a
name out of a search result and use it as an API field — check the endpoint's
schema with `get_endpoint_schema`.

Case metadata and opinion text also live on different endpoints. The
`opinions` endpoint holds a single opinion's text and authorship
(`plain_text`, `html_with_citations`, `author`, `type`). The case-level
metadata belongs to the cluster: `case_name`, `date_filed`, `citations`, and
`judges` are fields on `clusters`, not on `opinions`. An opinion record links
to its cluster via `cluster_id`.

# Reading document text

To read the text of an opinion or RECAP document, use the dedicated
`read_document` and `search_document` tools rather than fetching raw text
fields from the endpoints directly. These tools cache documents across users,
support paginated reading by character chunk, and let you grep for snippets
without loading the whole document. For opinions, they use the
`html_with_citations` field (the most reliable text source, with inline
citation markup); for RECAP documents, they use `plain_text`.

Opinion ids and cluster ids are separate id-spaces. A search result's
`cluster_id` is NOT an opinion id — pass the result's top-level `opinion_id`
to these tools, or pass `cluster_id` and they will resolve the cluster's
opinion(s) for you.

When fetching opinion or RECAP document records via `call_endpoint` or
`get_endpoint_item`, exclude text fields (`html_with_citations`, `plain_text`,
`html`, `html_lawbox`, etc.) from the fields you request — they can be
enormous and are better accessed through `read_document`.

Avoid trying to fetch PDFs directly, as the courtlistener storages urls are not
fetchable for AI agents.

# Linking to dockets and opinions

Docket and opinion URLs on courtlistener.com require *something* after the
ID (normally a case-name slug). Without it, the link 404s. When you don't
have a slug, repeat the resource name as the trailing segment:

    https://www.courtlistener.com/docket/{docket_id}/docket/
    https://www.courtlistener.com/opinion/{cluster_id}/opinion/

Note that opinion URLs take the *cluster* id, not an opinion id.

This is the safest format — it always resolves correctly even though it
looks redundant.
"""
