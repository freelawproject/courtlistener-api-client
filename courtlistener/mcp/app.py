import os

import sentry_sdk
from sentry_sdk.integrations.mcp import MCPIntegration

from courtlistener.mcp.server import create_http_app

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN") or None,
    integrations=[MCPIntegration()],
    traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE") or 0.02),
)

app = create_http_app()
