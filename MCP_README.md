# CourtListener MCP Server

A [FastMCP](https://github.com/jlowin/fastmcp) server that exposes the
[CourtListener API](https://www.courtlistener.com/help/api/rest/v4) to
[Model Context Protocol](https://modelcontextprotocol.io) clients. Use it to
let an MCP-capable LLM (Claude Desktop, Cursor, Goose, etc.) search opinions,
retrieve dockets, analyze citations, manage alerts, and more.

This document covers three things, in order:

1. [Connecting to the hosted server](#connecting-to-the-hosted-server) at
   `mcp.courtlistener.com` (the option most users want)
2. [Running the server locally](#running-the-server-locally) over stdio or HTTP
3. [Development and deployment](#development) of the server itself

---

## Connecting to the hosted server

Free Law Project hosts a public instance of this server at:

```
https://mcp.courtlistener.com/
```

It speaks the MCP [Streamable HTTP](https://modelcontextprotocol.io/specification/basic/transports#streamable-http)
transport. Any MCP client that supports Streamable HTTP with custom headers can
connect to it.

### Authentication

You need a CourtListener API token. Create one from your
[profile settings](https://www.courtlistener.com/profile/api/) (free account
required).

All requests must include the token in an `Authorization` header:

```
Authorization: Token <your-token-here>
```

Requests without a valid token will be rejected.

> **OAuth is coming soon.** Token-in-header auth is the current mechanism, but
> we plan to support OAuth so clients can connect without users having to
> copy-paste API tokens. This section will be updated when it lands.

### Client configuration

Most MCP clients accept a server URL and a set of headers. The exact
configuration format is client-specific; below is the shape of the values to
plug in:

| Field | Value |
| --- | --- |
| URL | `https://mcp.courtlistener.com/` |
| Transport | Streamable HTTP |
| Headers | `Authorization: Token <your-token-here>` |

For clients that only support stdio (for example, some older Claude Desktop
builds), you can bridge to the remote server with
[`mcp-remote`](https://www.npmjs.com/package/mcp-remote):

```json
{
  "mcpServers": {
    "courtlistener": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://mcp.courtlistener.com/",
        "--header",
        "Authorization: Token ${COURTLISTENER_API_TOKEN}"
      ],
      "env": {
        "COURTLISTENER_API_TOKEN": "your-token-here"
      }
    }
  }
}
```

### Programmatic access

If you want to call the server from code — for testing, scripting, or building
your own agent — use any MCP client library. See
[Calling the server from code](#calling-the-server-from-code) in the
Development section for an example.

---

## Running the server locally

You can also run the server on your own machine. Two transports are supported.

### stdio (recommended for local desktop clients)

The easiest way to run the stdio server is with
[`uvx`](https://docs.astral.sh/uv/guides/tools/), which fetches the
`courtlistener-api-client` package from PyPI and runs the
`courtlistener-mcp` console script (backed by `courtlistener.mcp.server:main`)
in an ephemeral environment — no manual install required. If you don't have
`uv` yet, follow the
[uv install instructions](https://docs.astral.sh/uv/getting-started/installation/).

Authentication in stdio mode uses the `COURTLISTENER_API_TOKEN` environment
variable (there is no request to attach headers to):

```bash
export COURTLISTENER_API_TOKEN="your-token-here"
uvx --from 'courtlistener-api-client[mcp]' courtlistener-mcp
```

A Claude Desktop–style config entry looks like this:

```json
{
  "mcpServers": {
    "courtlistener": {
      "command": "uvx",
      "args": [
        "--from",
        "courtlistener-api-client[mcp]",
        "courtlistener-mcp"
      ],
      "env": {
        "COURTLISTENER_API_TOKEN": "your-token-here"
      }
    }
  }
}
```

If you'd rather install the package into an environment yourself,
`pip install 'courtlistener-api-client[mcp]'` exposes the same
`courtlistener-mcp` command on your `PATH`.

stdio mode does not require Redis.

### HTTP (Streamable HTTP, same as the hosted server)

The HTTP app lives at `courtlistener.mcp.app:app` and is served by Uvicorn in
development or Gunicorn in production. The easiest way to run it is with
Docker Compose, which also starts a Redis instance for session state:

```bash
docker compose up --build
```

The server will be available at `http://localhost:8080/`. Connect to it the
same way you would connect to the hosted server, passing your token in an
`Authorization` header.

To point the server at a local CourtListener API instead of the public one,
set `COURTLISTENER_API_BASE_URL`. Because the MCP server runs inside a
container, use `host.docker.internal` to reach your host:

```bash
COURTLISTENER_API_BASE_URL=http://host.docker.internal:8000/api/rest/v4 \
  docker compose up --build
```

---

## Development

### Environment variables

| Variable | Used in | Description |
| --- | --- | --- |
| `COURTLISTENER_API_TOKEN` | stdio mode | API token used when no `Authorization` header is present. |
| `COURTLISTENER_API_BASE_URL` | both | Override the CourtListener API base URL. Defaults to the public API; set it to point at a local CourtListener dev instance. |
| `TARGET_ENV` | HTTP mode (Docker) | `dev` runs Uvicorn with `--reload`; `prod` runs Gunicorn. Set via the `docker-entrypoint.sh` script. |
| `REDIS_URL` | HTTP mode | Required. URL of the Redis instance used for MCP session state. |
| `MCP_WORKERS` | HTTP mode, prod | Number of Gunicorn workers. Defaults to `4`. |

### Project layout

The MCP code lives under `courtlistener/mcp/`:

- `server.py` — `create_mcp_server()` builds the FastMCP instance and wires up
  the tool-dispatch middleware. `main()` is the stdio entrypoint exposed as
  the `courtlistener-mcp` console script.
- `app.py` — imports `create_http_app()` from `server.py` and exposes `app`,
  the ASGI app that Gunicorn/Uvicorn serve.
- `middleware.py` — dispatches tool calls to the registry.
- `tools/` — one module per tool, registered in `tools/__init__.py`.

### Running against a local CourtListener

See the `COURTLISTENER_API_BASE_URL` instructions in the HTTP section above.
The same variable works in stdio mode if you prefer to iterate without Docker.

### Calling the server from code

Any MCP client library works against the running server — useful for smoke
tests, one-off scripts, or building your own agent. Here's an example against
the hosted server using the `fastmcp` Python client:

```python
import asyncio
import os

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport


async def main():
    async with Client(
        transport=StreamableHttpTransport(
            "https://mcp.courtlistener.com/",
            headers={
                "Authorization": f"Token {os.environ['COURTLISTENER_API_TOKEN']}"
            },
        ),
    ) as client:
        result = await client.call_tool(
            "get_endpoint_item",
            {"endpoint_id": "courts", "item_id": "scotus"},
        )
        print(result)


if __name__ == "__main__":
    asyncio.run(main())
```

Swap the URL for `http://localhost:8080/` to hit a locally running HTTP
instance instead.

### Tests and linting

Tests, linting, and type-checking run via `tox`:

```bash
tox
```

Run the pre-commit hooks (formatting, lint, etc.) across the whole repo with:

```bash
pre-commit run --all-files
```

CI runs the same targets on pull requests.

---

## Deployment

The hosted server is deployed from this repository. The
[`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) workflow runs on
every push to `main` and:

1. Builds a production Docker image (`TARGET_ENV=prod`) from the root
   `Dockerfile` and pushes it to Docker Hub as
   `freelawproject/courtlistener-mcp:<sha>-prod`.
2. Force-syncs the `mcp-env` ExternalSecret in the `courtlistener-mcp`
   namespace so fresh env values land before the rollout.
3. Rolls out the image to the `mcp-web` deployment in the `courtlistener`
   EKS cluster and waits for the rollout to complete.

PR labels can skip parts of the pipeline:

| Label | Effect |
| --- | --- |
| `skip-deploy` | Skip the build step (and therefore the whole deploy). |
| `skip-web-deploy` | Build and sync secrets, but don't roll out the new image. |
