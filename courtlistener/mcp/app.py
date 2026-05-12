import os

import sentry_sdk
from sentry_sdk.integrations.mcp import MCPIntegration

from courtlistener.mcp.server import create_http_app

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN") or None,
    integrations=[MCPIntegration()],
    traces_sample_rate=1.0,
)

app = create_http_app()
