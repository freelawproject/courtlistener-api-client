# Developer Documentation

## Getting Started

Clone the repo:

```sh
git clone https://github.com/freelawproject/courtlistener-api-client.git
cd courtlistener-api-client
```

Install the package with its dev dependencies:

```sh
uv sync --extra dev
```

Lint:

```sh
uv run pre-commit run --all-files
```

Type check:

```sh
uv run mypy
```

Test:

```sh
uv run tox
```

Test with integration tests, which hit the live API and need `COURTLISTENER_API_TOKEN`:

```sh
uv run tox -- --run-integration
```

## Adding a New Endpoint

### GET endpoints

Standard list and detail endpoints are generated from the API, so they need no handwritten code. `scripts/generate_models.py` reads every endpoint listed at the API root and its HTTP OPTIONS (fields, filters, lookups, choices and orderings), then writes a model per endpoint to `courtlistener/models/generated/endpoints/` and the shared filter models to `courtlistener/models/generated/filters/`. The client finds endpoints through those models, so a new endpoint is available as `client.<endpoint>` with `get` and `list` once its model exists.

The OPTIONS responses are cached in `docs/.src/http_options.json`. To pick up a new or changed endpoint, refresh the cache from the live API, then regenerate the docs:

```sh
COURTLISTENER_API_TOKEN=... uv run python scripts/generate_models.py --no-cache
uv run python scripts/generate_docs.py
```

Without `--no-cache`, the script regenerates the models from the cached file. The nightly `API Check` workflow runs the same steps and opens a PR when the API has changed. It authenticates with the `COURTLISTENER_TOKEN` repository secret. That token should belong to the CourtListener account `api-client-user`, whose credentials are saved in Bitwarden in the Development/AI collection.

Don't edit the generated models by hand; change `scripts/generate_models.py` or its templates in `scripts/templates/` and rerun it.

A GET endpoint that doesn't return the standard shape for `get` and `list` needs a custom module instead (see [Custom endpoints](#custom-endpoints)). `api-usage` is an example: it returns one document for the signed-in user instead of a paginated list, so it's left out of the generated models and served by `client.api_usage.get()`. Add such an endpoint to `CUSTOM_ENDPOINTS` in `scripts/generate_models.py`, so the generator skips it.

### Custom endpoints

Endpoints that need more than `get` and `list` (creating, updating or deleting records), or whose responses don't fit the standard `get` and `list` shape (like `api-usage`), get a handwritten module. Follow the existing ones: `alerts.py`, `docket_alerts.py`, `prayers.py`, `citation_lookup.py` and `api_usage.py`.

1. **Request models:** put the Pydantic models that validate the request in a module at the top of `courtlistener/models/`, such as `courtlistener/models/prayers.py` with `PrayersCreate`. Name the module after the endpoint (`docket_alerts.py` for `docket-alerts`) and its classes after the endpoint plus the operation (`DocketAlertsCreate`), to match the generated `DocketAlertsEndpoint`. Set `model_config = ConfigDict(extra="forbid")` so unknown arguments fail.
2. **Client module:** add `courtlistener/async_client/<name>.py`, one module per endpoint, with a class named after it (`AsyncDocketAlerts`). For an endpoint that also has a generated model, subclass `AsyncResource` with that model, so `get` and `list` keep working, and add the extra methods (see `AsyncPrayers`). Otherwise, write a small class that takes the client and calls `self._client._request(...)` (see `AsyncApiUsage`).
3. **Wire it up:** set it as an attribute in `AsyncCourtListener.__init__` (`self.prayers = AsyncPrayers(self)`), and export it from `courtlistener/async_client/__init__.py` and `courtlistener/__init__.py`.
4. **Sync client:** add the class's async-to-sync rename to `REPLACEMENTS` in `scripts/generate_sync_client.py` (`"AsyncPrayers": "Prayers"`), then generate the sync client (see [Updating the Client](#updating-the-client)) and export the sync class from `courtlistener/__init__.py`.
5. **Docs:** add a file for each new operation in `docs/.src/endpoint-operations/` (see [Generating Documentation](#generating-documentation)).
6. **Tests:** add tests for the new methods, such as `tests/test_async_prayers.py`.

## Updating the Client

The async client in `courtlistener/async_client/` is the handwritten source. The sync client in `courtlistener/sync_client/` is generated from it by `scripts/generate_sync_client.py`, which converts the async code to sync and renames the classes listed in `REPLACEMENTS`. Make every change in the async client, then regenerate:

```sh
uv run python scripts/generate_sync_client.py
```

Don't edit `courtlistener/sync_client/` by hand. Each file there says which async file it comes from, and the next regeneration overwrites manual changes.

## Generating Documentation

`scripts/generate_docs.py` writes the user-facing docs:

- **`docs/endpoints/<endpoint ID>.md`:** one page per endpoint. It has the endpoint's description, a GET section with the `get` and `list` calls, a link to the endpoint model, and a table of its fields (field, type, lookups, the number of choices, linked, and description). Sections follow for any other operations, then a Choices section with every choice list on the page, each collapsed. The search page has a field table per search type, built from the per-type search models.
- **`docs/README.md`:** the handwritten intro from `docs/.src/README.md`, followed by a table of every endpoint with its client attribute and operations.

Rerun it after changing the models or any doc source:

```sh
uv run python scripts/generate_docs.py
```

### Custom operations

Operations beyond `get` and `list` are documented by hand, one file per operation, in `docs/.src/endpoint-operations/`. Each file is named `<endpoint ID>.<operation>.md`, such as `docket-alerts.create.md`, and starts with front matter:

```markdown
---
method: POST
model: courtlistener.models.docket_alerts.DocketAlertsCreate
---
```

`method` (POST, PATCH, PUT or DELETE) is required. `model` is the Pydantic model that validates the request, and is optional. The generator adds each file to the endpoint's page under a section for its method, with a link to the model, or to the client method when there's no model. The rest of the file is the operation's documentation: a description, the call, and a field table. Write `(choices)` in a field's Choices cell to link to its choice list; choices that only the operation has go in a `## Choices` part at the end of the file. See that folder's README for details.

### Checks

The generator stops with an error if:

- A client resource has a public method beyond `get` and `list` with no operation file, or an operation file names a method the client doesn't have.
- An operation file has invalid front matter: a missing or unknown `method`, an unknown key, or a `model` that can't be imported.
- An operation's `(choices)` has no choice list to link to, or a page links to an anchor that's missing or used by two headings.
- `docs/endpoints/` has a page for an endpoint that no longer exists.

CI also regenerates the docs and the sync client, and fails if either differs from what's committed. That's the Documentation Check and Sync Client Check. Commit the regenerated files along with your change.
