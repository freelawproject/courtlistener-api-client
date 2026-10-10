"""Tests for authentication plumbing: Bearer vs Token headers in
``CourtListener.client``, the three-way resolution in
``MCPTool.get_client``, token resolution and caching in
the cached verifiers, and the server's auth wiring.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastmcp.server.auth.auth import AccessToken
from key_value.aio.stores.memory import MemoryStore
from redis.exceptions import ConnectionError as RedisConnectionError

from courtlistener import CourtListener
from courtlistener.mcp.auth import (
    ApiTokenVerifier,
    CourtListenerAuthBackend,
    CourtListenerOAuthProxy,
    OAuthTokenVerifier,
    cache_ttl,
)
from courtlistener.mcp.auth_types import TokenKind
from courtlistener.mcp.session import (
    InMemorySession,
    RedisSession,
    get_session,
    hmac_hex,
    set_session,
)
from courtlistener.mcp.settings import OAUTH_INTROSPECTION_URL
from courtlistener.settings import get_api_base_url


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
        from courtlistener.mcp.tools import MCP_TOOLS

        return MCP_TOOLS["get_counts"]

    def _verified(self, token, **claims):
        access_token = MagicMock()
        access_token.token = token
        access_token.claims = {"user_hash": "uh", **claims}
        return access_token

    def test_oauth_bearer_when_access_token_present(self):
        """With a FastMCP AccessToken available, use Bearer auth."""
        tool = self._get_tool()
        with patch(
            "courtlistener.mcp.tools.mcp_tool.get_access_token",
            return_value=self._verified(
                "oauth-jwt", token_kind=TokenKind.OAUTH
            ),
        ):
            cl = tool.get_client()
        assert cl.access_token == "oauth-jwt"
        assert cl.client.headers["Authorization"] == "Bearer oauth-jwt"

    def test_api_token_credential_uses_the_token_scheme(self):
        """A verified API token must go back out under DRF's ``Token``
        scheme — CL rejects an API token presented as Bearer."""
        tool = self._get_tool()
        with patch(
            "courtlistener.mcp.tools.mcp_tool.get_access_token",
            return_value=self._verified(
                "cl-api-token", token_kind=TokenKind.API
            ),
        ):
            cl = tool.get_client()
        assert cl.api_token == "cl-api-token"
        assert cl.access_token is None
        assert cl.client.headers["Authorization"] == "Token cl-api-token"

    def test_missing_kind_claim_defaults_to_bearer(self):
        """Defensive: an AccessToken with no ``token_kind`` claim is
        treated as OAuth rather than silently mis-schemed."""
        tool = self._get_tool()
        with patch(
            "courtlistener.mcp.tools.mcp_tool.get_access_token",
            return_value=self._verified("oauth-jwt"),
        ):
            cl = tool.get_client()
        assert cl.access_token == "oauth-jwt"
        assert cl.client.headers["Authorization"] == "Bearer oauth-jwt"

    def test_stdio_mode_env_var(self):
        """No verified credential (stdio: no HTTP layer exists) → the
        env var is the credential, resolved by the constructor."""
        tool = self._get_tool()
        with (
            patch(
                "courtlistener.mcp.tools.mcp_tool.get_access_token",
                return_value=None,
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


def http_response(status_code: int, payload=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=payload)
    return resp


def patch_http(response=None, side_effect=None):
    """Patch the httpx client the verification calls use."""
    http = MagicMock()
    http.get = AsyncMock(return_value=response, side_effect=side_effect)
    http.post = AsyncMock(return_value=response, side_effect=side_effect)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=http)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return patch(
        "courtlistener.mcp.auth.httpx.AsyncClient", return_value=ctx
    ), http


ACTIVE = {
    "active": True,
    "sub": "42",
    "username": "jane",
    "client_id": "some-client",
    "scope": "openid api",
    "exp": 1_900_000_000,
}


class TestVerifyOauthToken:
    """``OAuthTokenVerifier.check`` asks CourtListener whether a bearer token is
    active (RFC 7662), authenticating with the MCP server's own client
    credentials. There is no userinfo fallback: without credentials
    every bearer token is rejected."""

    @pytest.fixture(autouse=True)
    def client_credentials(self):
        with (
            patch("courtlistener.mcp.auth.OAUTH_CLIENT_ID", "mcp-client"),
            patch("courtlistener.mcp.auth.OAUTH_CLIENT_SECRET", "mcp-secret"),
        ):
            yield

    def test_an_active_token_resolves_to_the_sub_hmac(self):
        """``sub`` is the same OIDC subject userinfo returned, so user
        hashes survive the switch from userinfo to introspection."""
        client_patch, _ = patch_http(http_response(200, ACTIVE))
        with client_patch:
            info = run(OAuthTokenVerifier().check("tok"))
        assert info == {
            "user_hash": hmac_hex("42"),
            "scopes": ["openid", "api"],
            "expires_at": 1_900_000_000,
        }

    def test_posts_the_token_with_the_client_credentials(self):
        client_patch, http = patch_http(http_response(200, {"active": False}))
        with client_patch:
            run(OAuthTokenVerifier().check("tok"))
        assert http.post.await_args.args[0] == OAUTH_INTROSPECTION_URL
        assert http.post.await_args.kwargs["data"] == {
            "token": "tok",
            "token_type_hint": "access_token",
        }
        assert http.post.await_args.kwargs["auth"] == (
            "mcp-client",
            "mcp-secret",
        )

    def test_an_inactive_token_returns_none(self):
        client_patch, _ = patch_http(http_response(200, {"active": False}))
        with client_patch:
            assert run(OAuthTokenVerifier().check("tok")) is None

    def test_a_token_without_a_subject_returns_none(self):
        """A client-credentials token is active but belongs to no user;
        there is nobody to act as."""
        client_patch, _ = patch_http(
            http_response(200, {**ACTIVE, "sub": None, "username": None})
        )
        with client_patch:
            assert run(OAuthTokenVerifier().check("tok")) is None

    def test_a_token_without_an_expiry_still_resolves(self):
        payload = {**ACTIVE, "exp": None}
        client_patch, _ = patch_http(http_response(200, payload))
        with client_patch:
            info = run(OAuthTokenVerifier().check("tok"))
        assert info is not None
        assert info["expires_at"] is None

    @pytest.mark.parametrize("status", [401, 403, 500, 503])
    def test_non_200_fails_closed(self, status):
        client_patch, _ = patch_http(http_response(status, ACTIVE))
        with client_patch:
            assert run(OAuthTokenVerifier().check("tok")) is None

    @pytest.mark.parametrize("status", [401, 403])
    def test_rejected_client_credentials_log_an_error(self, status, caplog):
        """401/403 here mean *our* credentials are wrong, not the
        user's: every OAuth login is failing, so it must reach Sentry."""
        client_patch, _ = patch_http(http_response(status, ACTIVE))
        with client_patch, caplog.at_level("ERROR", "courtlistener.mcp.auth"):
            run(OAuthTokenVerifier().check("tok"))
        assert any(r.levelname == "ERROR" for r in caplog.records)

    def test_an_empty_scope_stays_empty(self):
        """``scope: ""`` must not read as "no scopes recorded"; the
        verifier only falls back to its required scopes for API tokens,
        which carry no ``scopes`` key at all."""
        client_patch, _ = patch_http(
            http_response(200, {**ACTIVE, "scope": ""})
        )
        with client_patch:
            info = run(OAuthTokenVerifier().check("tok"))
        assert info is not None
        assert info["scopes"] == []

    def test_network_error_returns_none(self):
        client_patch, _ = patch_http(side_effect=httpx.ConnectError("boom"))
        with client_patch:
            assert run(OAuthTokenVerifier().check("tok")) is None

    def test_missing_client_credentials_rejects_without_a_call(self):
        client_patch, http = patch_http(http_response(200, ACTIVE))
        with (
            client_patch,
            patch("courtlistener.mcp.auth.OAUTH_CLIENT_SECRET", None),
        ):
            assert run(OAuthTokenVerifier().check("tok")) is None
        http.post.assert_not_awaited()


class TestCacheTtl:
    """The verification cache never outlives the token it vouches for."""

    @pytest.fixture(autouse=True)
    def frozen_clock(self):
        with (
            patch("courtlistener.mcp.auth.time.time", return_value=1_000),
            patch("courtlistener.mcp.auth.TOKEN_CACHE_TTL_SECONDS", 600),
        ):
            yield

    def test_no_expiry_uses_the_configured_ttl(self):
        assert cache_ttl({"user_hash": "h"}) == 600
        assert cache_ttl({"user_hash": "h", "expires_at": None}) == 600

    def test_a_distant_expiry_uses_the_configured_ttl(self):
        assert cache_ttl({"user_hash": "h", "expires_at": 10_000}) == 600

    def test_a_near_expiry_cuts_the_ttl(self):
        assert cache_ttl({"user_hash": "h", "expires_at": 1_120}) == 120

    def test_an_expired_token_is_cached_for_one_second_at_most(self):
        assert cache_ttl({"user_hash": "h", "expires_at": 900}) == 1


class TestVerifyApiToken:
    """``ApiTokenVerifier.check`` checks a CourtListener API token against the
    API root, which lists the available endpoints and 401s for any bad
    credential (confirmed against production)."""

    def test_valid_token_resolves_to_the_token_hmac(self):
        client_patch, _ = patch_http(http_response(200))
        with client_patch:
            info = run(ApiTokenVerifier().check("cl-api-token"))
        assert info == {"user_hash": hmac_hex("cl-api-token")}

    def test_namespace_matches_the_stdio_fallback(self, monkeypatch):
        """An API token never rotates, so hashing it directly is stable
        — and it lands a user in the same namespace whether their token
        arrives over HTTP or via COURTLISTENER_API_TOKEN."""
        from courtlistener.mcp.session import user_key

        client_patch, _ = patch_http(http_response(200))
        with client_patch:
            info = run(ApiTokenVerifier().check("cl-api-token"))
        monkeypatch.setenv("COURTLISTENER_API_TOKEN", "cl-api-token")
        with patch(
            "courtlistener.mcp.session.get_access_token", return_value=None
        ):
            assert info["user_hash"] == user_key()

    def test_targets_the_api_root_with_the_token_scheme(self):
        client_patch, http = patch_http(http_response(200))
        with client_patch:
            run(ApiTokenVerifier().check("cl-api-token"))
        url = http.get.await_args.args[0]
        headers = http.get.await_args.kwargs["headers"]
        # Trailing slash included: the root 301s without it.
        assert url == f"{get_api_base_url()}/"
        assert headers["Authorization"] == "Token cl-api-token"

    def test_follows_a_configured_api_base_url(self):
        """A deployment pointed at staging must verify against staging,
        or a staging token would 401 at the door while working fine for
        every tool call."""
        staging = "https://staging.courtlistener.com/api/rest/v4"
        client_patch, http = patch_http(http_response(200))
        with (
            patch.dict("os.environ", {"COURTLISTENER_API_BASE_URL": staging}),
            client_patch,
        ):
            run(ApiTokenVerifier().check("cl-api-token"))
        assert http.get.await_args.args[0] == f"{staging}/"

    def test_a_throttle_is_not_a_successful_authentication(self):
        """Tempting to accept: DRF authenticates before it throttles, so
        a 429 *from Django* would prove the token is good. But CloudFront
        rate-limits in front of Django and those 429s never reach it —
        see #216, where the origin logged zero 429s while clients were
        getting them. Accepting 429 would let an edge blip verify any
        string at all, and the verifier would cache that for the
        token TTL, long outliving the blip.
        """
        client_patch, _ = patch_http(http_response(429))
        with client_patch:
            assert run(ApiTokenVerifier().check("cl-api-token")) is None

    @pytest.mark.parametrize("status", [401, 403])
    def test_rejected_token_returns_none(self, status):
        client_patch, _ = patch_http(http_response(status))
        with client_patch:
            assert run(ApiTokenVerifier().check("bad-token")) is None

    @pytest.mark.parametrize("status", [301, 302, 307])
    def test_a_redirect_is_not_a_successful_authentication(self, status):
        """The API root 301s without a trailing slash. If the success
        check were "anything below 400", a misconfigured URL would
        validate every token including garbage."""
        client_patch, _ = patch_http(http_response(status))
        with client_patch:
            assert run(ApiTokenVerifier().check("bad-token")) is None

    @pytest.mark.parametrize("status", [500, 502, 503])
    def test_server_error_fails_closed(self, status):
        """A CL blip must not mint a session for an unverified token."""
        client_patch, _ = patch_http(http_response(status))
        with client_patch:
            assert run(ApiTokenVerifier().check("cl-api-token")) is None

    def test_network_error_returns_none(self):
        client_patch, _ = patch_http(side_effect=httpx.ConnectError("boom"))
        with client_patch:
            assert run(ApiTokenVerifier().check("cl-api-token")) is None


class TestCachedTokenVerifier:
    """Each verifier sits between its caller and the session store: it
    serves a cached verification when one exists for that credential
    kind, and otherwise asks CourtListener and caches the answer."""

    @pytest.fixture(autouse=True)
    def fresh_session(self):
        set_session(InMemorySession())
        yield
        set_session(None)

    def test_verifies_and_caches_on_a_miss(self):
        verify = AsyncMock(return_value={"user_hash": "uh"})
        with patch(
            "courtlistener.mcp.auth.OAuthTokenVerifier.check", new=verify
        ):
            token = run(OAuthTokenVerifier().verify_token("tok"))
        assert token is not None
        assert token.claims == {
            "user_hash": "uh",
            "token_kind": TokenKind.OAUTH,
            "cached": False,
        }
        assert run(get_session().get_token_info("tok", TokenKind.OAUTH)) == {
            "user_hash": "uh"
        }

    def test_cache_hit_skips_verification_and_is_flagged(self):
        """A cache-served verification is flagged in the claims so the
        tool layer can triage downstream 401s (routine rotation vs.
        AS/API disagreement)."""
        verify = AsyncMock(return_value={"user_hash": "uh"})
        with patch(
            "courtlistener.mcp.auth.OAuthTokenVerifier.check", new=verify
        ):
            run(OAuthTokenVerifier().verify_token("tok"))
            token = run(OAuthTokenVerifier().verify_token("tok"))
        assert verify.await_count == 1
        assert token is not None
        assert token.claims["cached"] is True
        assert token.claims["user_hash"] == "uh"

    def test_a_cached_entry_does_not_cross_credential_kinds(self):
        """The kind is part of the cache key, so an entry verified as
        one kind can't satisfy a lookup for another. Without that, a
        warm entry would let a credential in under the wrong scheme."""
        verify_oauth = AsyncMock(return_value={"user_hash": "uh"})
        verify_api = AsyncMock(return_value=None)
        with (
            patch(
                "courtlistener.mcp.auth.OAuthTokenVerifier.check",
                new=verify_oauth,
            ),
            patch(
                "courtlistener.mcp.auth.ApiTokenVerifier.check", new=verify_api
            ),
        ):
            run(OAuthTokenVerifier().verify_token("tok"))
            assert run(ApiTokenVerifier().verify_token("tok")) is None
        verify_api.assert_awaited_once_with("tok")

    def test_api_verifier_asks_the_api(self):
        verify_oauth = AsyncMock(return_value={"user_hash": "oauth-uh"})
        verify_api = AsyncMock(return_value={"user_hash": "api-uh"})
        with (
            patch(
                "courtlistener.mcp.auth.OAuthTokenVerifier.check",
                new=verify_oauth,
            ),
            patch(
                "courtlistener.mcp.auth.ApiTokenVerifier.check", new=verify_api
            ),
        ):
            token = run(ApiTokenVerifier().verify_token("tok"))
        assert token is not None
        assert token.claims["user_hash"] == "api-uh"
        assert token.claims["token_kind"] == TokenKind.API
        verify_oauth.assert_not_awaited()
        assert run(get_session().get_token_info("tok", TokenKind.API)) == {
            "user_hash": "api-uh"
        }

    def test_cache_ttl_follows_the_token_expiry(self):
        info = {"user_hash": "uh", "scopes": ["api"], "expires_at": 5_000}
        session = MagicMock(
            get_token_info=AsyncMock(return_value=None),
            store_token_info=AsyncMock(),
        )
        set_session(session)
        with patch(
            "courtlistener.mcp.auth.OAuthTokenVerifier.check",
            new=AsyncMock(return_value=info),
        ):
            run(OAuthTokenVerifier().verify_token("tok"))
        session.store_token_info.assert_awaited_once_with(
            "tok", TokenKind.OAUTH, info, cache_ttl(info)
        )

    def test_failed_verification_is_not_cached(self):
        with patch(
            "courtlistener.mcp.auth.OAuthTokenVerifier.check",
            new=AsyncMock(return_value=None),
        ):
            assert run(OAuthTokenVerifier().verify_token("tok")) is None
        assert (
            run(get_session().get_token_info("tok", TokenKind.OAUTH)) is None
        )

    def test_empty_token_costs_no_round_trip(self):
        verify = AsyncMock()
        with patch(
            "courtlistener.mcp.auth.OAuthTokenVerifier.check", new=verify
        ):
            assert run(OAuthTokenVerifier().verify_token("")) is None
        verify.assert_not_awaited()

    def test_session_store_outage_degrades_to_direct_verification(self):
        """A session-store outage must not turn every request into a
        500. The degradation lives in the Redis backend — connection
        failures read as misses and skip writes — so the verifier
        itself carries no guards and verification runs uncached."""
        down = RedisConnectionError("redis down")
        session = RedisSession("redis://example.test:6379")
        session._client = MagicMock(
            get=AsyncMock(side_effect=down),
            set=AsyncMock(side_effect=down),
        )
        set_session(session)
        with patch(
            "courtlistener.mcp.auth.OAuthTokenVerifier.check",
            new=AsyncMock(return_value={"user_hash": "uh"}),
        ):
            token = run(OAuthTokenVerifier().verify_token("tok"))
        assert token is not None
        assert token.claims["user_hash"] == "uh"
        assert token.claims["cached"] is False

    def test_requires_only_the_api_scope(self):
        """``api`` is what CL's REST API expects downstream, and the
        middleware 403s a token without it. Introspection needs no
        particular scope, and ``scopes_supported`` is advertised by the
        proxy separately.
        """
        assert OAuthTokenVerifier().required_scopes == ["api"]
        assert ApiTokenVerifier().required_scopes == ["api"]

    def test_carries_introspected_scopes_and_expiry(self):
        """The middleware checks ``required_scopes`` against the
        token's own scopes and rejects it once ``expires_at`` passes,
        so both must come from introspection, not be echoed back."""
        with patch(
            "courtlistener.mcp.auth.OAuthTokenVerifier.check",
            new=AsyncMock(
                return_value={
                    "user_hash": "uh",
                    "scopes": ["openid", "api", "wiki"],
                    "expires_at": 1_900_000_000,
                }
            ),
        ):
            token = run(OAuthTokenVerifier().verify_token("tok"))
        assert token is not None
        assert token.scopes == ["openid", "api", "wiki"]
        assert token.expires_at == 1_900_000_000

    def test_does_not_grant_scopes_an_oauth_token_lacks(self):
        """An OAuth token introspected with no scope keeps none, so the
        middleware's ``api`` check rejects it; only an API token, which
        records no ``scopes`` at all, gets the required set."""
        with patch(
            "courtlistener.mcp.auth.OAuthTokenVerifier.check",
            new=AsyncMock(
                return_value={
                    "user_hash": "uh",
                    "scopes": [],
                    "expires_at": None,
                }
            ),
        ):
            token = run(OAuthTokenVerifier().verify_token("tok"))
        assert token is not None
        assert token.scopes == []

    def test_api_tokens_are_granted_the_required_scopes(self):
        with patch(
            "courtlistener.mcp.auth.ApiTokenVerifier.check",
            new=AsyncMock(return_value={"user_hash": "uh"}),
        ):
            token = run(ApiTokenVerifier().verify_token("tok"))
        assert token is not None
        assert token.scopes == ["api"]
        assert token.expires_at is None


class TestServerAuthWiring:
    """The HTTP factory always attaches the dual-scheme provider —
    there is no auth-off HTTP mode — while ``create_mcp_server`` itself
    stays auth-free so stdio remains credential-free."""

    def test_http_app_always_authenticates(self):
        """Regression guard for the removed ``MCP_REQUIRE_OAUTH`` flag,
        which fail-opened: any value other than exactly "true" silently
        deployed an unauthenticated server. The factory now wires auth
        with no conditional at all, and the setting itself is gone."""
        from starlette.middleware.authentication import (
            AuthenticationMiddleware,
        )

        import courtlistener.mcp.server as server_mod
        import courtlistener.mcp.settings as settings_mod

        assert not hasattr(settings_mod, "MCP_REQUIRE_OAUTH")
        with (
            patch.dict("os.environ", {"MCP_REQUIRE_OAUTH": "false"}),
            patch.object(server_mod, "REDIS_URL", "redis://localhost:6379"),
            patch.object(server_mod, "OAUTH_CLIENT_ID", "mcp-client"),
            patch.object(server_mod, "OAUTH_CLIENT_SECRET", "mcp-secret"),
            patch.object(server_mod, "get_oauth_store", MemoryStore),
        ):
            app = server_mod.create_http_app()
        assert AuthenticationMiddleware in [
            mw.cls for mw in app.user_middleware
        ]

    def test_http_app_requires_the_client_credentials(self):
        """There is no OAuth without the server's own CourtListener
        application: it is the client in every upstream exchange."""
        import courtlistener.mcp.server as server_mod

        with (
            patch.object(server_mod, "REDIS_URL", "redis://localhost:6379"),
            patch.object(server_mod, "OAUTH_CLIENT_ID", None),
            pytest.raises(ValueError, match="COURTLISTENER_OAUTH_CLIENT_ID"),
        ):
            server_mod.create_http_app()

    def test_create_mcp_server_does_not_enable_auth_by_default(self):
        """Bare ``create_mcp_server`` wires no auth — the HTTP factory
        attaches it explicitly, which is what keeps stdio (``main``)
        credential-free."""
        from courtlistener.mcp.server import create_mcp_server

        mcp = create_mcp_server()
        # FastMCP exposes its auth provider via ``auth`` (or ``_auth``
        # depending on version); both should be falsy here.
        auth = getattr(mcp, "auth", None) or getattr(mcp, "_auth", None)
        assert not auth


class TestUserKey:
    """``user_key`` prefers the OAuth ``user_hash`` claim (stable across
    token rotation) and falls back to an HMAC of the credential."""

    def test_reads_claim_from_oauth_context(self):
        from courtlistener.mcp.session import user_key

        fake_token = MagicMock()
        fake_token.claims = {"user_hash": "claim-derived-hash"}
        with patch(
            "courtlistener.mcp.session.get_access_token",
            return_value=fake_token,
        ):
            assert user_key() == "claim-derived-hash"

    def test_hashes_the_access_token_without_a_claim(self):
        from courtlistener.mcp.session import hmac_hex, user_key

        fake_token = MagicMock()
        fake_token.token = "bare-jwt"
        fake_token.claims = {}
        with patch(
            "courtlistener.mcp.session.get_access_token",
            return_value=fake_token,
        ):
            assert user_key() == hmac_hex("bare-jwt")

    def test_stdio_hashes_the_env_var_credential(self, monkeypatch):
        """No FastMCP access token (stdio) → HMAC the API token env var."""
        from courtlistener.mcp.session import hmac_hex, user_key

        monkeypatch.setenv("COURTLISTENER_API_TOKEN", "legacy-token")
        with patch(
            "courtlistener.mcp.session.get_access_token", return_value=None
        ):
            assert user_key() == hmac_hex("legacy-token")

    def test_raises_without_a_credential(self, monkeypatch):
        from courtlistener.mcp.session import user_key

        monkeypatch.delenv("COURTLISTENER_API_TOKEN", raising=False)
        with (
            patch(
                "courtlistener.mcp.session.get_access_token",
                return_value=None,
            ),
            pytest.raises(ValueError, match="[Nn]o credential"),
        ):
            user_key()


class TestTokenKindScheme:
    """Each ``TokenKind`` carries the ``Authorization`` scheme it
    arrives under; ``from_scheme`` is the lookup the auth backend uses
    to route a request."""

    def test_bearer_maps_to_oauth(self):
        assert TokenKind.from_scheme("Bearer") is TokenKind.OAUTH

    def test_token_maps_to_api(self):
        assert TokenKind.from_scheme("Token") is TokenKind.API

    def test_lookup_is_case_insensitive(self):
        """RFC 7235 schemes are case-insensitive; clients vary."""
        assert TokenKind.from_scheme("bearer") is TokenKind.OAUTH
        assert TokenKind.from_scheme("TOKEN") is TokenKind.API

    def test_unknown_scheme_returns_none(self):
        assert TokenKind.from_scheme("Basic") is None
        assert TokenKind.from_scheme("") is None

    def test_scheme_attribute_does_not_disturb_the_value(self):
        """The member's *value* feeds the cache key; the scheme rides
        alongside without changing it."""
        assert TokenKind.OAUTH.scheme == "bearer"
        assert TokenKind.API.scheme == "token"
        assert TokenKind.OAUTH.value == "oauth"
        assert TokenKind.API.value == "api_token"
        assert TokenKind("oauth") is TokenKind.OAUTH

    @pytest.mark.parametrize("kind", list(TokenKind))
    def test_every_kind_declares_a_scheme(self, kind):
        """Adding a ``TokenKind`` without a scheme mapping would make
        ``.scheme`` raise ``KeyError`` mid-request."""
        assert kind.scheme


class TestCourtListenerAuthBackend:
    """The SDK's ``BearerAuthBackend`` drops anything that isn't
    ``Bearer `` before the verifier sees it, so ``Token`` auth reads as
    "no credentials" without this backend. The scheme selects the
    credential kind and is binding — the inverted combinations are
    rejected, not retried the other way."""

    def _conn(self, auth_header):
        conn = MagicMock()
        conn.headers = (
            {} if auth_header is None else {"authorization": auth_header}
        )
        return conn

    def _backend(self, *, oauth=None, api=None):
        """A backend over a proxy and an API verifier that record how
        they were asked."""
        proxy = MagicMock(verify_token=AsyncMock(return_value=oauth))
        api_verifier = MagicMock(verify_token=AsyncMock(return_value=api))
        return CourtListenerAuthBackend(proxy, api_verifier), (
            proxy,
            api_verifier,
        )

    def _accepted(self):
        token = MagicMock()
        token.scopes = ["openid", "api"]
        token.expires_at = None
        token.client_id = "courtlistener-mcp"
        return token

    def test_token_scheme_goes_to_the_api_verifier(self):
        backend, (proxy, api) = self._backend(api=self._accepted())
        result = run(backend.authenticate(self._conn("Token cl-api-token")))
        assert result is not None
        api.verify_token.assert_awaited_once_with("cl-api-token")
        proxy.verify_token.assert_not_awaited()

    def test_bearer_scheme_goes_to_the_proxy(self):
        """Bearer is handed to the parent so the SDK keeps owning the
        MCP-token path, with the proxy as its verifier."""
        backend, (proxy, api) = self._backend(oauth=self._accepted())
        result = run(backend.authenticate(self._conn("Bearer oauth-jwt")))
        assert result is not None
        proxy.verify_token.assert_awaited_once_with("oauth-jwt")
        api.verify_token.assert_not_awaited()

    def test_scheme_match_is_case_insensitive(self):
        """RFC 7235 credential schemes are case-insensitive, and clients
        do vary (``token`` vs ``Token``)."""
        backend, (_, api) = self._backend(api=self._accepted())
        run(backend.authenticate(self._conn("token cl-api-token")))
        api.verify_token.assert_awaited_once_with("cl-api-token")

    def test_rejected_api_token_yields_no_user(self):
        backend, _ = self._backend(api=None)
        assert run(backend.authenticate(self._conn("Token nope"))) is None

    def test_rejections_are_counted_by_scheme_and_issuer(self):
        """A rejected MCP-issued token (JWT-shaped) and a rejected
        CourtListener token (opaque) must land in different series, or a
        broken MCP token path would hide inside the legacy-token noise."""
        from courtlistener.mcp.metrics import auth_rejections_total

        mcp = auth_rejections_total.labels(scheme="bearer", issuer="mcp")
        legacy = auth_rejections_total.labels(
            scheme="bearer", issuer="courtlistener"
        )
        api = auth_rejections_total.labels(
            scheme="token", issuer="courtlistener"
        )
        before = mcp._value.get(), legacy._value.get(), api._value.get()
        backend, _ = self._backend(oauth=None, api=None)
        run(backend.authenticate(self._conn("Bearer aaa.bbb.ccc")))
        run(
            backend.authenticate(
                self._conn("Bearer kzzpskQh6zphyXclrRWtUnvpjGVjxwjUOJtMGPU0")
            )
        )
        run(backend.authenticate(self._conn("Token nope")))
        run(backend.authenticate(self._conn("Basic abc")))
        assert (mcp._value.get(), legacy._value.get(), api._value.get()) == (
            before[0] + 1,
            before[1] + 1,
            before[2] + 1,
        )

    def test_accepted_credentials_are_not_counted(self):
        from courtlistener.mcp.metrics import auth_rejections_total

        mcp = auth_rejections_total.labels(scheme="bearer", issuer="mcp")
        before = mcp._value.get()
        backend, _ = self._backend(oauth=self._accepted())
        run(backend.authenticate(self._conn("Bearer a.b.c")))
        assert mcp._value.get() == before

    def test_expired_api_token_is_rejected(self):
        expired = self._accepted()
        expired.expires_at = 1
        backend, _ = self._backend(api=expired)
        assert run(backend.authenticate(self._conn("Token old"))) is None

    def test_unsupported_scheme_is_rejected(self):
        backend, (proxy, api) = self._backend(api=self._accepted())
        assert run(backend.authenticate(self._conn("Basic abc123"))) is None
        proxy.verify_token.assert_not_awaited()
        api.verify_token.assert_not_awaited()

    def test_missing_header_is_rejected(self):
        backend, (proxy, api) = self._backend(api=self._accepted())
        assert run(backend.authenticate(self._conn(None))) is None
        proxy.verify_token.assert_not_awaited()
        api.verify_token.assert_not_awaited()

    def test_empty_credential_costs_no_round_trip(self):
        backend, (_, api) = self._backend(api=self._accepted())
        assert run(backend.authenticate(self._conn("Token "))) is None
        api.verify_token.assert_not_awaited()


class TestCourtListenerOAuthProxy:
    """The proxy is FastMCP's ``OAuthProxy`` with one change: its auth
    backend also accepts ``Token`` credentials. Discovery, DCR,
    authorize, token and revocation routes are inherited untouched."""

    def test_installs_the_dual_scheme_backend(self):
        from starlette.middleware.authentication import (
            AuthenticationMiddleware,
        )

        proxy = _auth_provider()
        auth_mw = proxy.get_middleware()[0]
        assert auth_mw.cls is AuthenticationMiddleware
        backend = auth_mw.kwargs["backend"]
        assert isinstance(backend, CourtListenerAuthBackend)
        assert backend.token_verifier is proxy
        assert isinstance(backend.api_verifier, ApiTokenVerifier)

    def test_verifies_upstream_tokens_by_introspection(self):
        assert isinstance(
            _auth_provider()._token_validator, OAuthTokenVerifier
        )

    def test_publishes_the_authorization_server_routes(self):
        paths = {
            getattr(r, "path", None)
            for r in _auth_provider().get_routes(mcp_path="/")
        }
        assert {
            "/.well-known/oauth-protected-resource",
            "/.well-known/oauth-authorization-server",
            "/register",
            "/authorize",
            "/token",
            "/revoke",
        } <= paths


def _auth_provider():
    """The proxy create_http_app attaches, built for tests."""
    from courtlistener.mcp.settings import MCP_BASE_URL

    return CourtListenerOAuthProxy(
        upstream_authorization_endpoint="https://example.test/o/authorize/",
        upstream_token_endpoint="https://example.test/o/token/",
        upstream_revocation_endpoint="https://example.test/o/revoke_token/",
        upstream_client_id="mcp-client",
        upstream_client_secret="mcp-secret",
        valid_scopes=["openid", "api"],
        base_url=MCP_BASE_URL,
        client_storage=MemoryStore(),
        jwt_signing_key="test-signing-key",
    )


class TestAuthOverHttp:
    """End to end through FastMCP's middleware stack: the scheme has to
    survive the whole chain, not just our backend in isolation."""

    @pytest.fixture(autouse=True)
    def fresh_session(self):
        set_session(InMemorySession())
        yield
        set_session(None)

    def _app(self):
        from starlette.testclient import TestClient

        from courtlistener.mcp.server import create_mcp_server

        # Mirrors create_http_app's wiring, minus the Redis store.
        mcp = create_mcp_server(auth=_auth_provider())
        return TestClient(mcp.http_app(path="/"))

    def _initialize(self, headers):
        with self._app() as http_client:
            return http_client.post(
                "/",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "0"},
                    },
                },
                headers={
                    "Accept": "application/json, text/event-stream",
                    **headers,
                },
            )

    def _patch_verifiers(self, *, oauth_ok, api_ok):
        bearer = AccessToken(
            token="oauth-jwt",
            client_id="c",
            scopes=["api"],
            claims={"user_hash": "uh", "token_kind": "oauth", "cached": False},
        )
        return (
            patch(
                "courtlistener.mcp.auth.CourtListenerOAuthProxy.verify_token",
                new=AsyncMock(return_value=bearer if oauth_ok else None),
            ),
            patch(
                "courtlistener.mcp.auth.ApiTokenVerifier.check",
                new=AsyncMock(
                    return_value={"user_hash": "uh"} if api_ok else None
                ),
            ),
        )

    def test_api_token_is_accepted(self):
        oauth_patch, api_patch = self._patch_verifiers(
            oauth_ok=False, api_ok=True
        )
        with oauth_patch, api_patch:
            resp = self._initialize({"Authorization": "Token cl-api-token"})
        assert resp.status_code == 200

    def test_oauth_bearer_is_accepted(self):
        oauth_patch, api_patch = self._patch_verifiers(
            oauth_ok=True, api_ok=False
        )
        with oauth_patch, api_patch:
            resp = self._initialize({"Authorization": "Bearer oauth-jwt"})
        assert resp.status_code == 200

    def test_api_token_sent_as_bearer_is_rejected(self):
        """The inverted combination gets a 401, not a second chance:
        a Bearer credential is only ever checked as an MCP-issued token."""
        oauth_patch, api_patch = self._patch_verifiers(
            oauth_ok=False, api_ok=True
        )
        with oauth_patch, api_patch:
            resp = self._initialize({"Authorization": "Bearer cl-api-token"})
        assert resp.status_code == 401

    def test_oauth_token_sent_as_token_scheme_is_rejected(self):
        """The other inversion: a ``Token`` credential is only ever
        checked against CL's API."""
        oauth_patch, api_patch = self._patch_verifiers(
            oauth_ok=True, api_ok=False
        )
        with oauth_patch, api_patch:
            resp = self._initialize({"Authorization": "Token oauth-jwt"})
        assert resp.status_code == 401

    def test_missing_credentials_still_get_the_oauth_challenge(self):
        """Unauthenticated requests must keep advertising Bearer so
        OAuth discovery is untouched — ``Token`` support is deliberately
        not advertised in the RFC 6750 methods."""
        resp = self._initialize({})
        assert resp.status_code == 401
        assert resp.headers["www-authenticate"].startswith("Bearer")


class TestHealthEndpoint:
    """``/health`` must stay unauthenticated so uptime checks keep
    working even when OAuth is enabled on the MCP routes."""

    def test_health_is_unauthenticated_under_oauth(self):
        """GET /health returns 200 with no Authorization header, even
        when the HTTP app has an OAuth ``AuthProvider`` attached."""
        from starlette.testclient import TestClient

        from courtlistener.mcp.server import create_mcp_server

        # Skip create_http_app (it requires REDIS_URL); we only care
        # that /health routes through FastMCP's starlette app
        # unauthenticated, with the same provider attached.
        mcp = create_mcp_server(auth=_auth_provider())

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

        from courtlistener.mcp.server import create_mcp_server
        from courtlistener.mcp.settings import OPENAI_APPS_CHALLENGE_TOKEN

        token = OPENAI_APPS_CHALLENGE_TOKEN
        mcp = create_mcp_server(auth=_auth_provider())

        app = mcp.http_app(path="/")
        with TestClient(app) as http_client:
            response = http_client.get("/.well-known/openai-apps-challenge")
        assert response.status_code == 200
        assert response.text == token
        assert response.headers["content-type"].startswith("text/plain")
