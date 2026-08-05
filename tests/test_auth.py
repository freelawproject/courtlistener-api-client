"""Tests for authentication plumbing: Bearer vs Token headers in
``CourtListener.client``, the three-way resolution in
``MCPTool.get_client``, token resolution and caching in
``resolve_token``, and the server's auth wiring.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from courtlistener import CourtListener
from courtlistener.mcp.auth import (
    TOKEN_KIND_API,
    TOKEN_KIND_OAUTH,
    CourtListenerTokenVerifier,
    resolve_token,
)
from courtlistener.mcp.session import InMemorySession, get_session, set_session


def run(coro):
    return asyncio.run(coro)


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


class TestResolveToken:
    """``resolve_token`` sits between the verifier and the session
    store: it serves a cached verification when one exists for that
    credential kind, and otherwise verifies and caches."""

    @pytest.fixture(autouse=True)
    def fresh_session(self):
        set_session(InMemorySession())
        yield
        set_session(None)

    def test_verifies_and_caches_on_a_miss(self):
        verify = AsyncMock(return_value={"user_hash": "uh"})
        with patch("courtlistener.mcp.auth.verify_oauth_token", new=verify):
            info = run(resolve_token("tok", kind=TOKEN_KIND_OAUTH))
        assert info == {
            "user_hash": "uh",
            "kind": TOKEN_KIND_OAUTH,
            "cached": False,
        }
        assert run(get_session().get_token_info("tok", TOKEN_KIND_OAUTH)) == {
            "user_hash": "uh"
        }

    def test_kind_and_cached_are_not_persisted(self):
        """``kind`` already lives in the cache key, and ``cached`` is
        per-request state for the middleware — neither belongs in the
        stored record."""
        verify = AsyncMock(return_value={"user_hash": "uh"})
        with patch("courtlistener.mcp.auth.verify_oauth_token", new=verify):
            run(resolve_token("tok", kind=TOKEN_KIND_OAUTH))
        stored = run(get_session().get_token_info("tok", TOKEN_KIND_OAUTH))
        assert stored == {"user_hash": "uh"}

    def test_cache_hit_skips_verification(self):
        verify = AsyncMock(return_value={"user_hash": "uh"})
        with patch("courtlistener.mcp.auth.verify_oauth_token", new=verify):
            run(resolve_token("tok", kind=TOKEN_KIND_OAUTH))
            info = run(resolve_token("tok", kind=TOKEN_KIND_OAUTH))
        assert verify.await_count == 1
        assert info["cached"] is True
        assert info["user_hash"] == "uh"

    def test_a_cached_entry_does_not_cross_credential_kinds(self):
        """The kind is part of the cache key, so an entry verified as
        one kind can't satisfy a lookup for another. Without that, a
        warm entry would let a credential in under the wrong scheme."""
        verify = AsyncMock(return_value={"user_hash": "uh"})
        with patch("courtlistener.mcp.auth.verify_oauth_token", new=verify):
            run(resolve_token("tok", kind=TOKEN_KIND_OAUTH))
            # No verifier exists for this kind yet, so a cache hit is
            # the only way it could resolve — and it must not.
            assert run(resolve_token("tok", kind=TOKEN_KIND_API)) is None

    def test_unimplemented_kind_returns_none(self):
        assert run(resolve_token("tok", kind=TOKEN_KIND_API)) is None

    def test_failed_verification_is_not_cached(self):
        with patch(
            "courtlistener.mcp.auth.verify_oauth_token",
            new=AsyncMock(return_value=None),
        ):
            assert run(resolve_token("tok", kind=TOKEN_KIND_OAUTH)) is None
        assert (
            run(get_session().get_token_info("tok", TOKEN_KIND_OAUTH)) is None
        )

    def test_cache_read_failure_degrades_to_direct_verification(self):
        """A session-store outage must not turn every request into a
        500 — verification carries on without the cache."""

        class ExplodingSession(InMemorySession):
            async def _get(self, key):
                raise ConnectionError("redis down")

        set_session(ExplodingSession())
        with patch(
            "courtlistener.mcp.auth.verify_oauth_token",
            new=AsyncMock(return_value={"user_hash": "uh"}),
        ):
            info = run(resolve_token("tok", kind=TOKEN_KIND_OAUTH))
        assert info is not None
        assert info["user_hash"] == "uh"

    def test_cache_write_failure_does_not_escape(self):
        class ExplodingSession(InMemorySession):
            async def _set(self, key, value, ttl_seconds):
                raise ConnectionError("redis down")

        set_session(ExplodingSession())
        with patch(
            "courtlistener.mcp.auth.verify_oauth_token",
            new=AsyncMock(return_value={"user_hash": "uh"}),
        ):
            info = run(resolve_token("tok", kind=TOKEN_KIND_OAUTH))
        assert info is not None


class TestServerAuthWiring:
    """``build_auth`` activates when ``MCP_REQUIRE_OAUTH`` is set to "true",
    and ``create_mcp_server`` itself never pulls auth from the
    environment — the HTTP factory is the only caller that does."""

    def test_build_auth_returns_verifier_when_set(self):
        """OAuth on → returns a RemoteAuthProvider that publishes the
        RFC 9728 protected-resource metadata, wrapping the CourtListener
        verifier. Tokens are validated via CL's OIDC userinfo endpoint,
        and the resolved user_hash is cached in Redis so session state
        survives access-token rotation.
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
            import courtlistener.mcp.settings as settings_mod

            importlib.reload(settings_mod)
            importlib.reload(server_mod)
            auth = server_mod.build_auth()
            verifier_cls = server_mod.CourtListenerTokenVerifier
        assert isinstance(auth, RemoteAuthProvider)
        assert isinstance(auth.token_verifier, verifier_cls)
        # Discovery route is advertised so clients can find the auth
        # server without the MCP having to serve
        # .well-known/oauth-authorization-server itself.
        routes = auth.get_routes(mcp_path="/")
        paths = {getattr(r, "path", None) for r in routes}
        assert "/.well-known/oauth-protected-resource" in paths

    def test_verifier_declares_openid_and_api_scopes(self):
        """Required scopes must appear on the verifier so they're
        advertised in protected-resource metadata and MCP clients
        include them in the authorize request. ``openid`` is what
        makes userinfo accept the token at all; ``api`` is what CL's
        REST API expects downstream.
        """
        verifier = CourtListenerTokenVerifier(
            base_url="https://mcp.example.test"
        )
        assert set(verifier.required_scopes) == {"openid", "api"}

    def test_verifier_accepts_a_resolved_token(self):
        """Successful resolution → AccessToken carrying the user_hash
        and the credential kind in its claims, plus the required scopes
        echoed back so the middleware's scope check passes.
        """
        verifier = CourtListenerTokenVerifier(
            base_url="https://mcp.example.test"
        )
        with patch(
            "courtlistener.mcp.auth.resolve_token",
            new=AsyncMock(
                return_value={
                    "user_hash": "fake-user-hash",
                    "kind": TOKEN_KIND_OAUTH,
                    "cached": False,
                }
            ),
        ):
            token = run(verifier.verify_token("anything-goes"))
        assert token is not None
        assert token.token == "anything-goes"
        assert token.claims.get("user_hash") == "fake-user-hash"
        assert token.claims.get("token_kind") == TOKEN_KIND_OAUTH
        assert token.claims.get("cached") is False
        assert set(token.scopes) == {"openid", "api"}

    def test_verifier_asks_for_an_oauth_credential(self):
        """Bearer is the only scheme the SDK lets through today, so the
        verifier resolves against OAuth until API tokens are added."""
        verifier = CourtListenerTokenVerifier(
            base_url="https://mcp.example.test"
        )
        resolve = AsyncMock(
            return_value={
                "user_hash": "h",
                "kind": TOKEN_KIND_OAUTH,
                "cached": False,
            }
        )
        with patch("courtlistener.mcp.auth.resolve_token", new=resolve):
            run(verifier.verify_token("jwt"))
        resolve.assert_awaited_once_with("jwt", kind=TOKEN_KIND_OAUTH)

    def test_verifier_marks_cache_hits(self):
        """A cache-served verification is flagged in the claims so the
        middleware can triage downstream 401s (routine rotation vs.
        AS/API disagreement)."""
        verifier = CourtListenerTokenVerifier(
            base_url="https://mcp.example.test"
        )
        with patch(
            "courtlistener.mcp.auth.resolve_token",
            new=AsyncMock(
                return_value={
                    "user_hash": "fake-user-hash",
                    "kind": TOKEN_KIND_OAUTH,
                    "cached": True,
                }
            ),
        ):
            token = run(verifier.verify_token("cached-token"))
        assert token is not None
        assert token.claims.get("cached") is True

    def test_verifier_rejects_an_unresolvable_token(self):
        """Resolution returning ``None`` (401/non-200/network error) →
        ``verify_token`` returns ``None``, which the auth middleware
        converts into a proper HTTP 401 with ``WWW-Authenticate`` so
        the MCP client re-runs OAuth.
        """
        verifier = CourtListenerTokenVerifier(
            base_url="https://mcp.example.test"
        )
        with patch(
            "courtlistener.mcp.auth.resolve_token",
            new=AsyncMock(return_value=None),
        ):
            token = run(verifier.verify_token("revoked-or-bad"))
        assert token is None

    def test_verifier_rejects_empty_token(self):
        """Empty bearer → short-circuit without touching the cache or
        userinfo. Prevents trivially-empty ``Authorization: Bearer``
        headers from consuming a round-trip to CL.
        """
        verifier = CourtListenerTokenVerifier(
            base_url="https://mcp.example.test"
        )
        resolve = AsyncMock()
        with patch("courtlistener.mcp.auth.resolve_token", new=resolve):
            assert run(verifier.verify_token("")) is None
        resolve.assert_not_awaited()

    def test_build_auth_respects_require_oauth_setting(self):
        """``build_auth`` reads ``settings.MCP_REQUIRE_OAUTH`` at call
        time, so it can be patched like any other setting."""
        from courtlistener.mcp.server import build_auth

        with patch("courtlistener.mcp.settings.MCP_REQUIRE_OAUTH", False):
            assert build_auth() is None
        with patch("courtlistener.mcp.settings.MCP_REQUIRE_OAUTH", True):
            assert build_auth() is not None

    def test_require_oauth_parses_true_case_insensitively(self):
        """``MCP_REQUIRE_OAUTH=TRUE`` / ``True`` also enables OAuth."""
        import importlib

        import courtlistener.mcp.settings as settings_mod

        try:
            for value in ("true", "TRUE", "True"):
                with patch.dict("os.environ", {"MCP_REQUIRE_OAUTH": value}):
                    importlib.reload(settings_mod)
                    assert settings_mod.MCP_REQUIRE_OAUTH is True, value
        finally:
            importlib.reload(settings_mod)

    def test_require_oauth_ignores_other_truthy_values(self):
        """Only the literal string ``true`` (any casing) enables OAuth.

        Prevents accidental activation from stray values like ``1`` or
        ``yes`` in deployment configs.
        """
        import importlib

        import courtlistener.mcp.settings as settings_mod

        try:
            for value in ("1", "yes", "on", "True ", " true", "false", ""):
                with patch.dict("os.environ", {"MCP_REQUIRE_OAUTH": value}):
                    importlib.reload(settings_mod)
                    assert settings_mod.MCP_REQUIRE_OAUTH is False, value
        finally:
            importlib.reload(settings_mod)

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
        from courtlistener.mcp.session import user_hash

        client = CourtListener(access_token="any-token")
        fake_token = MagicMock()
        fake_token.claims = {"user_hash": "claim-derived-hash"}
        with patch(
            "courtlistener.mcp.session.get_access_token",
            return_value=fake_token,
        ):
            assert user_hash(client) == "claim-derived-hash"

    def test_falls_back_to_api_token_hmac_outside_oauth_context(self):
        """Legacy / stdio path: no FastMCP context → HMAC the API token
        directly, matching pre-OAuth behavior.
        """
        from courtlistener.mcp.session import hmac_hex, user_hash

        client = CourtListener(api_token="legacy-token")
        with patch(
            "courtlistener.mcp.session.get_access_token",
            side_effect=RuntimeError("no HTTP request"),
        ):
            assert user_hash(client) == hmac_hex("legacy-token")

    def test_raises_when_client_has_no_credential(self):
        """Defensive: a client with neither an access token nor an API
        token should never reach the session store."""
        from courtlistener.mcp.session import user_hash

        client = CourtListener.__new__(CourtListener)
        client.api_token = None
        client.access_token = None
        with (
            patch(
                "courtlistener.mcp.session.get_access_token",
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
            import courtlistener.mcp.settings as settings_mod

            importlib.reload(settings_mod)
            importlib.reload(server_mod)
            mcp = server_mod.create_mcp_server(auth=server_mod.build_auth())

        app = mcp.http_app(path="/")
        with TestClient(app) as http_client:
            response = http_client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"
        assert body["services"] == {"mcp": True}


class TestOpenAIAppsChallenge:
    """The OpenAI Apps domain-verification challenge must be served
    publicly (unauthenticated) so OpenAI can fetch it even when OAuth is
    enabled on the MCP routes."""

    def test_challenge_is_unauthenticated_under_oauth(self):
        """GET /.well-known/openai-apps-challenge returns the token as
        plain text with no Authorization header, even when the HTTP app
        has an OAuth ``AuthProvider`` attached."""
        from starlette.testclient import TestClient

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
            import courtlistener.mcp.settings as settings_mod

            importlib.reload(settings_mod)
            importlib.reload(server_mod)
            mcp = server_mod.create_mcp_server(auth=server_mod.build_auth())
            token = server_mod.OPENAI_APPS_CHALLENGE_TOKEN

        app = mcp.http_app(path="/")
        with TestClient(app) as http_client:
            response = http_client.get("/.well-known/openai-apps-challenge")
        assert response.status_code == 200
        assert response.text == token
        assert response.headers["content-type"].startswith("text/plain")
