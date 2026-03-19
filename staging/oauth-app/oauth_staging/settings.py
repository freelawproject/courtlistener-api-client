"""Minimal Django settings for the staging OAuth app.

This app exists solely to simulate CourtListener's auth system for
testing the MCP server's OAuth integration. It is disposable — delete
it when CL ships real OAuth.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "staging-insecure-key-do-not-use-in-production",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() == "true"

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "oauth2_provider",
    "oauth_staging",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "oauth_staging.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "oauth_staging" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "oauth_staging.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/admin/login/"

# --- django-oauth-toolkit settings ---
# Mirrors what CL would configure when adding OAuth support.

OAUTH2_PROVIDER = {
    # Use PKCE (required by MCP spec)
    "PKCE_REQUIRED": True,
    # Scopes the MCP server can request
    "SCOPES": {
        "read": "Read access to CourtListener API",
        "write": "Write access (alerts, subscriptions)",
    },
    "DEFAULT_SCOPES": ["read"],
    # Allow all grant types for testing
    "ALLOWED_GRANT_TYPES": [
        "authorization-code",
    ],
    # Access tokens expire after 1 hour
    "ACCESS_TOKEN_EXPIRE_SECONDS": 3600,
    # Refresh tokens expire after 30 days
    "REFRESH_TOKEN_EXPIRE_SECONDS": 2592000,
    # Support token introspection (RFC 7662)
    "RESOURCE_SERVER_INTROSPECTION_URL": None,  # self-hosted
}
