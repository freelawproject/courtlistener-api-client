import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parents[1]

# Redis connection URL. In-memory storage is used when unset.
REDIS_URL = os.getenv("REDIS_URL")

# Deployed git SHA, reported by /health.
GIT_SHA = os.getenv("GIT_SHA", "unknown")

# Public base URL of this MCP server (the OAuth resource identifier).
MCP_BASE_URL = os.getenv("MCP_BASE_URL", "https://mcp.courtlistener.com")

# OAuth authorization server.
OAUTH_ISSUER = os.getenv(
    "COURTLISTENER_OAUTH_ISSUER", "https://www.courtlistener.com"
)

OAUTH_USERINFO_URL = os.getenv(
    "COURTLISTENER_OAUTH_USERINFO_URL",
    f"{OAUTH_ISSUER.rstrip('/')}/o/userinfo/",
)

# HMAC key for hashing tokens and user identifiers into storage keys.
MCP_SECRET_KEY = os.getenv("MCP_SECRET_KEY")
if not MCP_SECRET_KEY:
    MCP_SECRET_KEY = "insecure-do-not-use-in-production"
    logger.warning(
        "MCP_SECRET_KEY is not set; falling back to an insecure default. "
        "Set a strong random value before going to production."
    )
MCP_SECRET_BYTES = MCP_SECRET_KEY.encode("utf-8")

# Sentry config
SENTRY_DSN = os.getenv("SENTRY_DSN") or None
SENTRY_TRACES_SAMPLE_RATE = float(
    os.getenv("SENTRY_TRACES_SAMPLE_RATE") or 0.02
)

# How long a verified token's info is cached.
TOKEN_CACHE_TTL_SECONDS = int(os.getenv("MCP_TOKEN_CACHE_TTL", "600"))

# Session-scoped state (query pagination, citation jobs) lives this long.
SESSION_TTL_SECONDS = 3600  # 1 hour

# How long a cached document lives in the session store (shared across users).
DOCUMENT_TTL_SECONDS = 86400  # 24 hours

# Timeout for the upstream calls made during token verification.
VERIFICATION_TIMEOUT_SECONDS = 20

# Result-count bounds for search/list tools.
DEFAULT_NUM_RESULTS = 20
MAX_NUM_RESULTS = 100

# Domain-verification token for the OpenAI Apps directory listing.
OPENAI_APPS_CHALLENGE_TOKEN = "oR-QatCh96AHxvH1yYTS7_oP4ByrYVSuoCmAifKJyVg"
