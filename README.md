# CourtListener API Client

A Python client for the [CourtListener API](https://www.courtlistener.com/api/rest/v4/), providing access to millions of legal opinions, dockets, judges, and more from [Free Law Project](https://free.law/).

## Installation

```bash
pip install courtlistener-api-client
```

## Authentication

You'll need a CourtListener API token. You can get one by [creating an account](https://www.courtlistener.com/register/) and generating a token in your [profile settings](https://www.courtlistener.com/profile/api/).

Set it as an environment variable:

```bash
export COURTLISTENER_API_TOKEN="your-token-here"
```

Or pass it directly to the client:

```python
from courtlistener import CourtListener

client = CourtListener(api_token="your-token-here")
```

## Quickstart

```python
from courtlistener import CourtListener

client = CourtListener()

# Get a specific opinion by ID
opinion = client.opinions.get(1)

# Search for opinions
response = client.opinions.list(cluster__case_name="Miranda")

# Access results from the current page
for opinion in response.results:
    print(opinion)

# Check the total count of matching results
print(response.count)

# Iterate through all results across pages
response = client.dockets.list(court="scotus")
for docket in response:
    print(docket)
```

### Pagination

List queries return a `ResourceIterator` that handles pagination automatically:

```python
results = client.dockets.list(court="scotus")

# Iterate through all results across all pages
for docket in results:
    print(docket)

# Or navigate pages manually
results = client.dockets.list(court="scotus")
print(results.results)   # current page results

if results.has_next():
    results.next()
    print(results.results)  # next page results
```

## Available Endpoints

Access any endpoint as an attribute on the client. Each endpoint supports `.get(id)` and `.list(**filters)`.

| Endpoint | Description |
| --- | --- |
| `search` | General search across all types |
| `opinion_search` | Search opinions |
| `recap_search` | Search RECAP archive |
| `dockets` | Court dockets |
| `docket_entries` | Docket entries |
| `recap_documents` | RECAP documents |
| `opinions` | Court opinions |
| `opinions_cited` | Citation relationships |
| `clusters` | Opinion clusters |
| `courts` | Court information |
| `audio` | Oral argument audio |
| `people` | Judges and other persons |
| `positions` | Judge positions |
| `parties` | Case parties |
| `attorneys` | Attorneys |
| `financial_disclosures` | Financial disclosures |
| `alerts` | User alerts |
| `docket_alerts` | Docket alerts |
| `tags` | User-created tags |
| `visualizations` | Visualization data |
| `schools` | Schools |
| `educations` | Judge education records |
| `political_affiliations` | Political affiliations |
| `aba_ratings` | ABA ratings |
| `fjc_integrated_database` | FJC integrated database |

See the [CourtListener API docs](https://www.courtlistener.com/api/rest-info/) for the full list and available filters.
