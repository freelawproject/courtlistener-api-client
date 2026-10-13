import sentry_sdk
from sentry_sdk.integrations.mcp import MCPIntegration

from courtlistener.mcp.exceptions import before_send
from courtlistener.mcp.server import create_http_app
from courtlistener.mcp.settings import SENTRY_DSN, SENTRY_TRACES_SAMPLE_RATE

sentry_sdk.init(
    dsn=SENTRY_DSN,
    integrations=[MCPIntegration()],
    traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
    before_send=before_send,
)

app = create_http_app()
