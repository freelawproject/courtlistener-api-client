import base64
import hashlib
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parents[1]

GIT_SHA = os.getenv("GIT_SHA", "unknown")

# Redis connection URL. In-memory storage is used when unset.
REDIS_URL = os.getenv("REDIS_URL")

# Postgres for the OAuth token store.
POSTGRES_CONFIGURED = bool(os.getenv("PGHOST"))
PGHOST = os.getenv("PGHOST") or "localhost"
PGPORT = int(os.getenv("PGPORT") or 5432)
PGUSER = os.getenv("PGUSER")
PGPASSWORD = os.getenv("PGPASSWORD")
PGDATABASE = os.getenv("PGDATABASE") or "postgres"
PGPOOL_MAX = int(os.getenv("PGPOOL_MAX") or 4)

# Public base URL of this MCP server (the OAuth resource identifier).
MCP_BASE_URL = os.getenv("MCP_BASE_URL", "https://mcp.courtlistener.com")

# HMAC key for hashing tokens and user identifiers into storage keys.
MCP_SECRET_KEY = os.getenv("MCP_SECRET_KEY")
if not MCP_SECRET_KEY:
    MCP_SECRET_KEY = "insecure-do-not-use-in-production"
    logger.warning(
        "MCP_SECRET_KEY is not set; falling back to an insecure default. "
        "Set a strong random value before going to production."
    )
MCP_SECRET_BYTES = MCP_SECRET_KEY.encode("utf-8")

# Fernet key encrypting the OAuth store's values.
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

# CourtListener, the identity provider this server brokers logins for.
OAUTH_ISSUER = os.getenv(
    "COURTLISTENER_OAUTH_ISSUER", "https://www.courtlistener.com"
).rstrip("/")
OAUTH_AUTHORIZATION_URL = f"{OAUTH_ISSUER}/o/authorize/"
OAUTH_TOKEN_URL = f"{OAUTH_ISSUER}/o/token/"
OAUTH_REVOCATION_URL = f"{OAUTH_ISSUER}/o/revoke_token/"
OAUTH_INTROSPECTION_URL = os.getenv(
    "COURTLISTENER_OAUTH_INTROSPECTION_URL", f"{OAUTH_ISSUER}/o/introspect/"
)

# This server's own confidential OAuth application at CourtListener.
OAUTH_CLIENT_ID = os.getenv("COURTLISTENER_OAUTH_CLIENT_ID")
OAUTH_CLIENT_SECRET = os.getenv("COURTLISTENER_OAUTH_CLIENT_SECRET")
OAUTH_SCOPES = os.getenv(
    "COURTLISTENER_OAUTH_SCOPES", "openid api wiki email profile"
).split()

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
