"""Authentication headers on the sync ``CourtListener`` client."""

from unittest.mock import patch

import pytest

from courtlistener import CourtListener


class TestClientAuthHeader:
    def test_api_token_uses_token_scheme(self):
        """``api_token=`` → ``Authorization: Token <token>``."""
        cl = CourtListener(api_token="secret-api-token")
        assert cl.client.headers["Authorization"] == "Token secret-api-token"

    def test_access_token_uses_bearer_scheme(self):
        """``access_token=`` → ``Authorization: Bearer <token>``."""
        cl = CourtListener(access_token="oauth-jwt")
        assert cl.client.headers["Authorization"] == "Bearer oauth-jwt"

    def test_access_token_takes_precedence_over_env(self):
        """``access_token`` wins over ``COURTLISTENER_API_TOKEN``."""
        with patch.dict(
            "os.environ", {"COURTLISTENER_API_TOKEN": "env-token"}
        ):
            cl = CourtListener(access_token="oauth-jwt")
        assert cl.access_token == "oauth-jwt"
        assert cl.api_token is None
        assert cl.client.headers["Authorization"] == "Bearer oauth-jwt"

    def test_env_var_fallback(self):
        """No explicit creds → fall back to env var with Token scheme."""
        with patch.dict(
            "os.environ", {"COURTLISTENER_API_TOKEN": "env-token"}
        ):
            cl = CourtListener()
        assert cl.client.headers["Authorization"] == "Token env-token"

    def test_missing_credentials_raises(self):
        """No creds and no env var → ValueError."""
        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(ValueError, match="Authentication is required"),
        ):
            CourtListener()

    def test_explicit_api_token_beats_env(self):
        """Explicit ``api_token`` wins over the env var."""
        with patch.dict(
            "os.environ", {"COURTLISTENER_API_TOKEN": "env-token"}
        ):
            cl = CourtListener(api_token="explicit")
        assert cl.client.headers["Authorization"] == "Token explicit"
