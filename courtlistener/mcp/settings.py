import base64
import hashlib
import logging
import os
from pathlib import Path

from courtlistener.settings import get_api_base_url

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parents[1]

# Redis connection URL. In-memory storage is used when unset.
REDIS_URL = os.getenv("REDIS_URL")

# Whether Postgres vars are configured for the OAuth token store.
POSTGRES_CONFIGURED = bool(os.getenv("PGHOST"))

# Deployed git SHA, reported by /health.
GIT_SHA = os.getenv("GIT_SHA", "unknown")

# Public base URL of this MCP server (the OAuth resource identifier).
MCP_BASE_URL = os.getenv("MCP_BASE_URL", "https://mcp.courtlistener.com")

# CourtListener: the identity provider this server brokers logins for.
OAUTH_ISSUER = os.getenv(
    "COURTLISTENER_OAUTH_ISSUER", "https://www.courtlistener.com"
)
_OAUTH_BASE = OAUTH_ISSUER.rstrip("/")
OAUTH_AUTHORIZATION_URL = f"{_OAUTH_BASE}/o/authorize/"
OAUTH_TOKEN_URL = f"{_OAUTH_BASE}/o/token/"
OAUTH_REVOCATION_URL = f"{_OAUTH_BASE}/o/revoke_token/"
OAUTH_INTROSPECTION_URL = f"{_OAUTH_BASE}/o/introspect/"

# This server's own (confidential) OAuth application at CourtListener.
OAUTH_CLIENT_ID = os.getenv("COURTLISTENER_OAUTH_CLIENT_ID")
OAUTH_CLIENT_SECRET = os.getenv("COURTLISTENER_OAUTH_CLIENT_SECRET")

# What this server asks CourtListener for on the user's behalf: scopes, and
# the RFC 8707 resources the resulting token is valid at.
OAUTH_SCOPES = os.getenv(
    "COURTLISTENER_OAUTH_SCOPES", "openid api wiki email"
).split()
OAUTH_RESOURCES = os.getenv(
    "COURTLISTENER_OAUTH_RESOURCES",
    f"{get_api_base_url().rstrip('/')}/ https://wiki.free.law",
).split()

# CourtListener refresh tokens expire after 30 days.
OAUTH_REFRESH_TOKEN_LIFETIME_SECONDS = 30 * 86400

# HMAC key for hashing tokens and user identifiers into storage keys.
MCP_SECRET_KEY = os.getenv("MCP_SECRET_KEY")
if not MCP_SECRET_KEY:
    MCP_SECRET_KEY = "insecure-do-not-use-in-production"
    logger.warning(
        "MCP_SECRET_KEY is not set; falling back to an insecure default. "
        "Set a strong random value before going to production."
    )
MCP_SECRET_BYTES = MCP_SECRET_KEY.encode("utf-8")

# Fernet key encrypting stored CourtListener tokens.
MCP_STORAGE_ENCRYPTION_KEY = os.getenv(
    "MCP_STORAGE_ENCRYPTION_KEY", ""
).encode()
if not MCP_STORAGE_ENCRYPTION_KEY:
    logger.warning(
        "MCP_STORAGE_ENCRYPTION_KEY is not set; deriving it from MCP_SECRET_KEY."
    )
    MCP_STORAGE_ENCRYPTION_KEY = base64.urlsafe_b64encode(
        hashlib.sha256(MCP_SECRET_BYTES + b":storage").digest()
    )

# Key signing the access tokens this server issues to MCP clients.
MCP_JWT_SIGNING_KEY: str | bytes = os.getenv("MCP_JWT_SIGNING_KEY", "")
if not MCP_JWT_SIGNING_KEY:
    logger.warning(
        "MCP_JWT_SIGNING_KEY is not set; deriving it from MCP_SECRET_KEY."
    )
    MCP_JWT_SIGNING_KEY = hashlib.sha256(MCP_SECRET_BYTES + b":jwt").digest()

# Sentry config
SENTRY_DSN = os.getenv("SENTRY_DSN") or None
SENTRY_TRACES_SAMPLE_RATE = float(
    os.getenv("SENTRY_TRACES_SAMPLE_RATE") or 0.05
)

# How long a verified token's info is cached.
TOKEN_CACHE_TTL_SECONDS = int(os.getenv("MCP_TOKEN_CACHE_TTL", "600"))

# Session-scoped state (query pagination, citation jobs) lives this long.
SESSION_TTL_SECONDS = 3600  # 1 hour

# How long a cached document lives in the session store (shared across users).
DOCUMENT_TTL_SECONDS = 86400  # 24 hours

# How long each day's active-user set is kept.
ACTIVE_USERS_TTL_SECONDS = 60 * 86400  # 60 days

# Timeout for the upstream calls made during token verification.
VERIFICATION_TIMEOUT_SECONDS = 20

# Result-count bounds for search/list tools.
DEFAULT_NUM_RESULTS = 20
MAX_NUM_RESULTS = 100

# Domain-verification token for the OpenAI Apps directory listing.
OPENAI_APPS_CHALLENGE_TOKEN = "oR-QatCh96AHxvH1yYTS7_oP4ByrYVSuoCmAifKJyVg"
