"""Tests for authentication plumbing: Bearer vs Token headers in
``CourtListener.client`` and the three-way resolution in
``MCPTool.get_client``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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


class TestMCPToolGetClient:
    """``MCPTool.get_client`` picks the right credential source."""

    def _get_tool(self):
        # Import lazily so tests don't require optional MCP deps to load.
        from courtlistener.mcp.tools.mcp_tool import MCPTool

        return MCPTool()

    def test_oauth_bearer_when_access_token_present(self):
        """With a FastMCP AccessToken available, use Bearer auth."""
        tool = self._get_tool()
        fake_token = MagicMock()
        fake_token.token = "oauth-jwt"
        with (
            patch(
                "courtlistener.mcp.tools.mcp_tool.get_access_token",
                return_value=fake_token,
            ),
            patch(
                "courtlistener.mcp.tools.mcp_tool.get_http_request"
            ) as mock_req,
        ):
            cl = tool.get_client()
        # The access-token path short-circuits before we touch the
        # HTTP request, so get_http_request should not be consulted.
        mock_req.assert_not_called()
        assert cl.access_token == "oauth-jwt"
        assert cl.client.headers["Authorization"] == "Bearer oauth-jwt"

    def test_legacy_token_header_pass_through(self):
        """No OAuth token, but an ``Authorization: Token …`` header → Token."""
        tool = self._get_tool()
        request = MagicMock()
        request.headers = {"Authorization": "Token legacy-api-token"}
        with (
            patch(
                "courtlistener.mcp.tools.mcp_tool.get_access_token",
                return_value=None,
            ),
            patch(
                "courtlistener.mcp.tools.mcp_tool.get_http_request",
                return_value=request,
            ),
        ):
            cl = tool.get_client()
        assert cl.api_token == "legacy-api-token"
        assert cl.access_token is None
        assert cl.client.headers["Authorization"] == "Token legacy-api-token"

    def test_stdio_mode_env_var(self):
        """No OAuth, no HTTP request → env var."""
        tool = self._get_tool()
        with (
            patch(
                "courtlistener.mcp.tools.mcp_tool.get_access_token",
                return_value=None,
            ),
            patch(
                "courtlistener.mcp.tools.mcp_tool.get_http_request",
                side_effect=RuntimeError("no HTTP request"),
            ),
            patch.dict(
                "os.environ",
                {"COURTLISTENER_API_TOKEN": "env-api-token"},
            ),
        ):
            cl = tool.get_client()
        assert cl.api_token == "env-api-token"
        assert cl.access_token is None
        assert cl.client.headers["Authorization"] == "Token env-api-token"

    def test_http_mode_without_auth_header_falls_back_to_env(self):
        """HTTP request present but no Authorization header → env var."""
        tool = self._get_tool()
        request = MagicMock()
        request.headers = {}
        with (
            patch(
                "courtlistener.mcp.tools.mcp_tool.get_access_token",
                return_value=None,
            ),
            patch(
                "courtlistener.mcp.tools.mcp_tool.get_http_request",
                return_value=request,
            ),
            patch.dict(
                "os.environ",
                {"COURTLISTENER_API_TOKEN": "env-api-token"},
            ),
        ):
            cl = tool.get_client()
        assert cl.client.headers["Authorization"] == "Token env-api-token"


class TestServerAuthWiring:
    """``build_auth`` only activates when ``MCP_REQUIRE_OAUTH`` is set,
    and ``create_mcp_server`` itself never pulls auth from the
    environment — the HTTP factory is the only caller that does."""

    def test_build_auth_returns_none_when_unset(self):
        from courtlistener.mcp.server import build_auth

        with patch.dict("os.environ", {}, clear=True):
            assert build_auth() is None

    def test_build_auth_returns_verifier_when_set(self):
        from fastmcp.server.auth.providers.jwt import JWTVerifier

        with patch.dict(
            "os.environ",
            {
                "MCP_REQUIRE_OAUTH": "1",
                "COURTLISTENER_OAUTH_ISSUER": "https://example.test",
                "MCP_BASE_URL": "https://mcp.example.test",
            },
        ):
            # Reload so module-level constants pick up the patched env.
            import importlib

            import courtlistener.mcp.server as server_mod

            importlib.reload(server_mod)
            auth = server_mod.build_auth()
        assert isinstance(auth, JWTVerifier)

    def test_create_mcp_server_does_not_enable_auth_by_default(self):
        """Bare ``create_mcp_server`` should not wire in OAuth, even
        when ``MCP_REQUIRE_OAUTH`` is set — only the HTTP factory does.
        """
        from courtlistener.mcp.server import create_mcp_server

        with patch.dict("os.environ", {"MCP_REQUIRE_OAUTH": "1"}):
            mcp = create_mcp_server()
        # FastMCP exposes its auth provider via ``auth`` (or ``_auth``
        # depending on version); both should be falsy here.
        auth = getattr(mcp, "auth", None) or getattr(mcp, "_auth", None)
        assert not auth
