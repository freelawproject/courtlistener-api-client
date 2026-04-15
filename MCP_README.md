# CourtListener MCP Server

The CourtListener MCP server is a FastMCP server that provides a MCP interface to the CourtListener API.

## Remote MCP Server

### Environment

--------------------------------
| Variable | Description |
| --- | --- |
| `TARGET_ENV` | Whether to run the server in `prod` or `dev` mode. |
| `REDIS_URL` | The URL of the Redis server. |
| `MCP_WORKERS` | The number of gunicorn workers to run the server with in `prod` mode. |
| `COURTLISTENER_API_BASE_URL` | The base URL of the CourtListener API. Defaults to the real CourtListener API base URL, but can be overridden to use a local development API. |
--------------------------------

### Development

Run the server in development mode with Docker Compose. The default environment variables are set in the compose file, so no env config is needed.

```bash
docker compose up --build
```

The server will be available at `http://localhost:8080`.

If you want to point to a local CourtListener instance, you can set the `COURTLISTENER_API_BASE_URL` environment variable to the base URL of the local API. Because the MCP server is running in a Docker container, you can use the `host.docker.internal` hostname to point to your host machine's `localhost`. For example:

```bash
COURTLISTENER_API_BASE_URL=http://host.docker.internal:8000/api/rest/v4
```

Here is an example script to make a test tool call to the server:

```python
import asyncio
import os

from dotenv import load_dotenv
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

load_dotenv()

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8080")
COURTLISTENER_API_TOKEN = os.getenv("COURTLISTENER_API_TOKEN")


async def main():
    async with Client(
        transport=StreamableHttpTransport(
            MCP_SERVER_URL,
            headers={"Authorization": f"Token {COURTLISTENER_API_TOKEN}"},
        ),
    ) as client:
        result = await client.call_tool(
            "get_endpoint_item", {"endpoint_id": "courts", "item_id": "scotus"}
        )
        print(result)


if __name__ == "__main__":
    asyncio.run(main())
```