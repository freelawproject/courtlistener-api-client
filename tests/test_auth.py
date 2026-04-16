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
        """OAuth on → returns a RemoteAuthProvider that publishes the
        RFC 9728 protected-resource metadata, wrapping the pass-through
        verifier. Token validation itself is delegated downstream to
        CL's OAuth2Authentication when the tool code forwards the
        bearer to the CourtListener API.
        """
        from fastmcp.server.auth.auth import RemoteAuthProvider

        with patch.dict(
            "os.environ",
            {
                "MCP_REQUIRE_OAUTH": "true",
                "COURTLISTENER_OAUTH_ISSUER": "https://example.test",
                "MCP_BASE_URL": "https://mcp.example.test",
            },
        ):
            # Reload so module-level constants pick up the patched env.
            # Re-read the class from the reloaded module so isinstance()
            # sees the new class object, not a stale reference.
            import importlib

            import courtlistener.mcp.server as server_mod

            importlib.reload(server_mod)
            auth = server_mod.build_auth()
            verifier_cls = server_mod.PassThroughTokenVerifier
        assert isinstance(auth, RemoteAuthProvider)
        assert isinstance(auth.token_verifier, verifier_cls)
        # Discovery route is advertised so clients can find the auth
        # server without the MCP having to serve
        # .well-known/oauth-authorization-server itself.
        routes = auth.get_routes(mcp_path="/")
        paths = {getattr(r, "path", None) for r in routes}
        assert "/.well-known/oauth-protected-resource" in paths

    def test_pass_through_verifier_accepts_any_non_empty_token(self):
        """Non-empty bearer tokens are accepted without local checks;
        CL is the authoritative validator downstream.
        """
        import asyncio

        from courtlistener.mcp.server import PassThroughTokenVerifier

        verifier = PassThroughTokenVerifier(
            base_url="https://mcp.example.test"
        )
        token = asyncio.run(verifier.verify_token("anything-goes"))
        assert token is not None
        assert token.token == "anything-goes"

    def test_pass_through_verifier_rejects_empty_token(self):
        """Empty bearer → not authenticated. Prevents trivially-empty
        ``Authorization: Bearer`` headers from slipping through.
        """
        import asyncio

        from courtlistener.mcp.server import PassThroughTokenVerifier

        verifier = PassThroughTokenVerifier(
            base_url="https://mcp.example.test"
        )
        assert asyncio.run(verifier.verify_token("")) is None

    def test_build_auth_accepts_true_case_insensitively(self):
        """``MCP_REQUIRE_OAUTH=TRUE`` / ``True`` also enables OAuth."""
        from courtlistener.mcp.server import build_auth

        for value in ("true", "TRUE", "True"):
            with patch.dict("os.environ", {"MCP_REQUIRE_OAUTH": value}):
                assert build_auth() is not None, value

    def test_build_auth_ignores_other_truthy_values(self):
        """Only the literal string ``true`` (any casing) enables OAuth.

        Prevents accidental activation from stray values like ``1`` or
        ``yes`` in deployment configs.
        """
        from courtlistener.mcp.server import build_auth

        for value in ("1", "yes", "on", "True ", " true", "false", ""):
            with patch.dict("os.environ", {"MCP_REQUIRE_OAUTH": value}):
                assert build_auth() is None, value

    def test_create_mcp_server_does_not_enable_auth_by_default(self):
        """Bare ``create_mcp_server`` should not wire in OAuth, even
        when ``MCP_REQUIRE_OAUTH`` is set — only the HTTP factory does.
        """
        from courtlistener.mcp.server import create_mcp_server

        with patch.dict("os.environ", {"MCP_REQUIRE_OAUTH": "true"}):
            mcp = create_mcp_server()
        # FastMCP exposes its auth provider via ``auth`` (or ``_auth``
        # depending on version); both should be falsy here.
        auth = getattr(mcp, "auth", None) or getattr(mcp, "_auth", None)
        assert not auth


class TestHealthEndpoint:
    """``/health`` must stay unauthenticated so uptime checks keep
    working even when OAuth is enabled on the MCP routes."""

    def test_health_is_unauthenticated_under_oauth(self):
        """GET /health returns 200 with no Authorization header, even
        when the HTTP app has a ``JWTVerifier`` attached."""
        from starlette.testclient import TestClient

        # Skip the RedisStore wiring (create_http_app requires Redis);
        # we only care that /health routes through FastMCP's starlette
        # app unauthenticated. Build the server the same way
        # create_http_app does — auth via build_auth().
        with patch.dict(
            "os.environ",
            {
                "MCP_REQUIRE_OAUTH": "true",
                "COURTLISTENER_OAUTH_ISSUER": "https://example.test",
                "MCP_BASE_URL": "https://mcp.example.test",
            },
        ):
            import importlib

            import courtlistener.mcp.server as server_mod

            importlib.reload(server_mod)
            mcp = server_mod.create_mcp_server(auth=server_mod.build_auth())

        app = mcp.http_app(path="/")
        with TestClient(app) as http_client:
            response = http_client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"
        assert body["services"] == {"mcp": True}
