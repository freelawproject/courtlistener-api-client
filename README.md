# CourtListener API Client

A Python client for the [CourtListener API](https://www.courtlistener.com/help/api/rest/v4), providing access to millions of legal opinions, dockets, judges, and more from [Free Law Project](https://free.law/).

> **Using an LLM?** See the [CourtListener MCP](https://github.com/freelawproject/courtlistener-mcp) and its [documentation](https://wiki.free.law/c/courtlistener/help/api/mcp).

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
for opinion in response.get_results():
    print(opinion)

# Check the total count of matching results
print(response.get_count())

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
print(results.get_results())  # current page results

if results.has_next():
    results.next()
    print(results.get_results())  # next page results
```

### Lookups

A field's lookups are the comparisons you can filter it by, beyond an exact match. The endpoint pages list them after each field, as in `date_filed: string (date) (lookups: gt, gte, lt, lte, range, …)`. Add one to a field name with a double underscore, or pass a dict of lookups:

```python
client.clusters.list(date_filed__gte="2020-01-01")
client.clusters.list(date_filed={"gte": "2020-01-01", "lt": "2021-01-01"})
```

Fields that point at another endpoint take filters on that endpoint the same way, such as `client.opinions.list(cluster__case_name="Miranda")`.

## Available Endpoints

For the full list of endpoints and details about their operations, see the [documentation](docs/README.md).

## API usage and rate limits

`client.api_usage.get()` returns your live throttle usage per scope and rate,
daily request counts for the last 14 days, and membership status. The endpoint
has its own throttle scope, so checking usage never spends the quota being
checked and it stays reachable when you are rate limited.

```python
usage = client.api_usage.get()

for row in usage["current_usage"]:
    print(row["scope"], row["rate"], row["remaining"], row["reset_at"])

print(usage["historical_usage"]["total"])
```

## Async

`AsyncCourtListener` mirrors `CourtListener` method for method. Anything that
makes a request is awaited, iteration uses `async for`, and the client is an
async context manager.

```python
from courtlistener import AsyncCourtListener

async with AsyncCourtListener() as client:
    opinion = await client.opinions.get(1)

    results = client.dockets.list(court="scotus")
    async for docket in results:
        print(docket)
```
