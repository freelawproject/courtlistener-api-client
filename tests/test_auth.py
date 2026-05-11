"""Tests for authentication plumbing: Bearer vs Token headers in
``CourtListener.client`` and the three-way resolution in
``MCPTool.get_client``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

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
    """``build_auth`` activates when ``MCP_REQUIRE_OAUTH`` is set to "true",
    and ``create_mcp_server`` itself never pulls auth from the
    environment — the HTTP factory is the only caller that does."""

    def test_build_auth_returns_verifier_when_set(self):
        """OAuth on → returns a RemoteAuthProvider that publishes the
        RFC 9728 protected-resource metadata, wrapping the userinfo
        verifier. Tokens are now validated via CL's OIDC userinfo
        endpoint, and the resolved user_hash is cached in Redis so
        session state survives access-token rotation.
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
            import courtlistener.mcp.tools.utils as utils_mod

            importlib.reload(utils_mod)
            importlib.reload(server_mod)
            auth = server_mod.build_auth()
            verifier_cls = server_mod.UserInfoTokenVerifier
        assert isinstance(auth, RemoteAuthProvider)
        assert isinstance(auth.token_verifier, verifier_cls)
        # Discovery route is advertised so clients can find the auth
        # server without the MCP having to serve
        # .well-known/oauth-authorization-server itself.
        routes = auth.get_routes(mcp_path="/")
        paths = {getattr(r, "path", None) for r in routes}
        assert "/.well-known/oauth-protected-resource" in paths

    def test_userinfo_verifier_declares_openid_and_api_scopes(self):
        """Required scopes must appear on the verifier so they're
        advertised in protected-resource metadata and MCP clients
        include them in the authorize request. ``openid`` is what
        makes userinfo accept the token at all; ``api`` is what CL's
        REST API expects downstream.
        """
        from courtlistener.mcp.auth import UserInfoTokenVerifier

        verifier = UserInfoTokenVerifier(base_url="https://mcp.example.test")
        assert set(verifier.required_scopes) == {"openid", "api"}

    def test_userinfo_verifier_accepts_when_userinfo_succeeds(self):
        """Successful userinfo lookup → AccessToken carrying the
        resolved ``user_hash`` in its claims, plus the required scopes
        echoed back so the middleware's scope check passes.
        """
        import asyncio

        from courtlistener.mcp.auth import UserInfoTokenVerifier

        verifier = UserInfoTokenVerifier(base_url="https://mcp.example.test")
        with patch(
            "courtlistener.mcp.auth.resolve_user_hash_via_userinfo",
            new=AsyncMock(return_value="fake-user-hash"),
        ):
            token = asyncio.run(verifier.verify_token("anything-goes"))
        assert token is not None
        assert token.token == "anything-goes"
        assert token.claims.get("user_hash") == "fake-user-hash"
        assert set(token.scopes) == {"openid", "api"}

    def test_userinfo_verifier_rejects_when_userinfo_fails(self):
        """Userinfo returning ``None`` (401/non-200/network error) →
        ``verify_token`` returns ``None``, which the auth middleware
        converts into a proper HTTP 401 with ``WWW-Authenticate`` so
        the MCP client re-runs OAuth.
        """
        import asyncio

        from courtlistener.mcp.auth import UserInfoTokenVerifier

        verifier = UserInfoTokenVerifier(base_url="https://mcp.example.test")
        with patch(
            "courtlistener.mcp.auth.resolve_user_hash_via_userinfo",
            new=AsyncMock(return_value=None),
        ):
            token = asyncio.run(verifier.verify_token("revoked-or-bad"))
        assert token is None

    def test_userinfo_verifier_rejects_empty_token(self):
        """Empty bearer → short-circuit without calling userinfo.
        Prevents trivially-empty ``Authorization: Bearer`` headers from
        consuming a round-trip to CL.
        """
        import asyncio

        from courtlistener.mcp.auth import UserInfoTokenVerifier

        verifier = UserInfoTokenVerifier(base_url="https://mcp.example.test")
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


class TestUserHash:
    """``user_hash`` picks between OAuth claims (new, stable across token
    rotation) and a direct HMAC of the legacy API token (old behavior).
    """

    def test_reads_claim_from_oauth_context(self):
        """With a FastMCP access token in scope carrying a ``user_hash``
        claim (populated by ``UserInfoTokenVerifier``), ``user_hash``
        returns the claim verbatim. Rotating the access token doesn't
        change the hash because the claim is derived from the stable
        OIDC ``sub``.
        """
        from courtlistener.mcp.tools.utils import user_hash

        client = CourtListener(access_token="any-token")
        fake_token = MagicMock()
        fake_token.claims = {"user_hash": "claim-derived-hash"}
        with patch(
            "courtlistener.mcp.tools.utils.get_access_token",
            return_value=fake_token,
        ):
            assert user_hash(client) == "claim-derived-hash"

    def test_falls_back_to_api_token_hmac_outside_oauth_context(self):
        """Legacy / stdio path: no FastMCP context → HMAC the API token
        directly, matching pre-OAuth behavior.
        """
        from courtlistener.mcp.tools.utils import hmac_hex, user_hash

        client = CourtListener(api_token="legacy-token")
        with patch(
            "courtlistener.mcp.tools.utils.get_access_token",
            side_effect=RuntimeError("no HTTP request"),
        ):
            assert user_hash(client) == hmac_hex("legacy-token")

    def test_raises_when_client_has_no_credential(self):
        """Defensive: a client with neither an access token nor an API
        token should never reach the Redis layer."""
        from courtlistener.mcp.tools.utils import user_hash

        client = CourtListener.__new__(CourtListener)
        client.api_token = None
        client.access_token = None
        with (
            patch(
                "courtlistener.mcp.tools.utils.get_access_token",
                side_effect=RuntimeError("no HTTP request"),
            ),
            pytest.raises(ValueError, match="no credential"),
        ):
            user_hash(client)


class TestHealthEndpoint:
    """``/health`` must stay unauthenticated so uptime checks keep
    working even when OAuth is enabled on the MCP routes."""

    def test_health_is_unauthenticated_under_oauth(self):
        """GET /health returns 200 with no Authorization header, even
        when the HTTP app has an OAuth ``AuthProvider`` attached."""
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
