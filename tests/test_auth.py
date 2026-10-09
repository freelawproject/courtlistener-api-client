"""Tests for authentication plumbing: Bearer vs Token headers in
``CourtListener.client``, the three-way resolution in
``MCPTool.get_client``, token resolution and caching in
``resolve_token``, and the server's auth wiring.
"""

from __future__ import annotations

import asyncio
import base64
import time
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from key_value.aio.stores.memory import MemoryStore
from redis.exceptions import ConnectionError as RedisConnectionError
from starlette.middleware.authentication import AuthenticationMiddleware

from courtlistener import CourtListener
from courtlistener.mcp.auth import (
    CourtListenerAuthBackend,
    CourtListenerOAuthProxy,
    CourtListenerTokenVerifier,
    ResourceIndicatorClient,
    cache_ttl,
    introspect_token,
    resolve_token,
    verify_api_token,
)
from courtlistener.mcp.auth_types import TokenKind
from courtlistener.mcp.session import (
    InMemorySession,
    RedisSession,
    get_session,
    hmac_hex,
    set_session,
)
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


def http_response(status_code: int):
    resp = MagicMock()
    resp.status_code = status_code
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


class TestVerifyApiToken:
    """``verify_api_token`` checks a CourtListener API token against the
    API root, which lists the available endpoints and 401s for any bad
    credential (confirmed against production)."""

    def test_valid_token_resolves_to_the_token_hmac(self):
        client_patch, _ = patch_http(http_response(200))
        with client_patch:
            info = run(verify_api_token("cl-api-token"))
        assert info == {"user_hash": hmac_hex("cl-api-token")}

    def test_namespace_matches_the_stdio_fallback(self, monkeypatch):
        """An API token never rotates, so hashing it directly is stable
        — and it lands a user in the same namespace whether their token
        arrives over HTTP or via COURTLISTENER_API_TOKEN."""
        from courtlistener.mcp.session import user_key

        client_patch, _ = patch_http(http_response(200))
        with client_patch:
            info = run(verify_api_token("cl-api-token"))
        monkeypatch.setenv("COURTLISTENER_API_TOKEN", "cl-api-token")
        with patch(
            "courtlistener.mcp.session.get_access_token", return_value=None
        ):
            assert info["user_hash"] == user_key()

    def test_targets_the_api_root_with_the_token_scheme(self):
        client_patch, http = patch_http(http_response(200))
        with client_patch:
            run(verify_api_token("cl-api-token"))
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
            run(verify_api_token("cl-api-token"))
        assert http.get.await_args.args[0] == f"{staging}/"

    def test_a_throttle_is_not_a_successful_authentication(self):
        """Tempting to accept: DRF authenticates before it throttles, so
        a 429 *from Django* would prove the token is good. But CloudFront
        rate-limits in front of Django and those 429s never reach it —
        see #216, where the origin logged zero 429s while clients were
        getting them. Accepting 429 would let an edge blip verify any
        string at all, and `resolve_token` would cache that for the
        token TTL, long outliving the blip.
        """
        client_patch, _ = patch_http(http_response(429))
        with client_patch:
            assert run(verify_api_token("cl-api-token")) is None

    @pytest.mark.parametrize("status", [401, 403])
    def test_rejected_token_returns_none(self, status):
        client_patch, _ = patch_http(http_response(status))
        with client_patch:
            assert run(verify_api_token("bad-token")) is None

    @pytest.mark.parametrize("status", [301, 302, 307])
    def test_a_redirect_is_not_a_successful_authentication(self, status):
        """The API root 301s without a trailing slash. If the success
        check were "anything below 400", a misconfigured URL would
        validate every token including garbage."""
        client_patch, _ = patch_http(http_response(status))
        with client_patch:
            assert run(verify_api_token("bad-token")) is None

    @pytest.mark.parametrize("status", [500, 502, 503])
    def test_server_error_fails_closed(self, status):
        """A CL blip must not mint a session for an unverified token."""
        client_patch, _ = patch_http(http_response(status))
        with client_patch:
            assert run(verify_api_token("cl-api-token")) is None

    def test_network_error_returns_none(self):
        client_patch, _ = patch_http(side_effect=httpx.ConnectError("boom"))
        with client_patch:
            assert run(verify_api_token("cl-api-token")) is None


def introspection(body, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body
    return resp


class TestIntrospectToken:
    """``introspect_token`` asks CourtListener whether an access token is
    active (RFC 7662), authenticating as the MCP server's own application,
    and keeps the subject, scopes, and expiry for the cache."""

    @pytest.fixture(autouse=True)
    def upstream_client(self):
        with patch.multiple(
            "courtlistener.mcp.auth",
            OAUTH_CLIENT_ID="mcp-app",
            OAUTH_CLIENT_SECRET="s3cret",
        ):
            yield

    def test_active_token_resolves_to_the_subject_hmac(self):
        patcher, http = patch_http(
            introspection(
                {
                    "active": True,
                    "sub": "3",
                    "username": "mcp_tester",
                    "scope": "openid api wiki email",
                    "exp": 1_900_000_000,
                }
            )
        )
        with patcher:
            info = run(introspect_token("cl-token"))
        assert info == {
            "user_hash": hmac_hex("3"),
            "scopes": ["openid", "api", "wiki", "email"],
            "expires_at": 1_900_000_000,
        }
        kwargs = http.post.await_args.kwargs
        assert kwargs["auth"] == ("mcp-app", "s3cret")
        assert kwargs["data"] == {
            "token": "cl-token",
            "token_type_hint": "access_token",
        }

    def test_inactive_token_returns_none(self):
        patcher, _ = patch_http(introspection({"active": False}))
        with patcher:
            assert run(introspect_token("revoked")) is None

    def test_a_subject_is_required(self):
        patcher, _ = patch_http(
            introspection({"active": True, "scope": "api"})
        )
        with patcher:
            assert run(introspect_token("odd")) is None

    @pytest.mark.parametrize("status", [401, 403, 500])
    def test_non_200_returns_none(self, status):
        patcher, _ = patch_http(introspection({}, status_code=status))
        with patcher:
            assert run(introspect_token("tok")) is None

    def test_network_error_returns_none(self):
        patcher, _ = patch_http(side_effect=httpx.ConnectError("down"))
        with patcher:
            assert run(introspect_token("tok")) is None

    def test_without_upstream_credentials_nothing_is_sent(self):
        patcher, http = patch_http(introspection({"active": True, "sub": "3"}))
        with patcher, patch("courtlistener.mcp.auth.OAUTH_CLIENT_ID", None):
            assert run(introspect_token("tok")) is None
        http.post.assert_not_awaited()


class TestCacheTtl:
    """A verification is cached for the configured TTL, but never past
    the token's own expiry."""

    def test_defaults_to_the_configured_ttl(self):
        from courtlistener.mcp.settings import TOKEN_CACHE_TTL_SECONDS

        assert cache_ttl({"user_hash": "h"}) == TOKEN_CACHE_TTL_SECONDS
        assert (
            cache_ttl({"user_hash": "h", "expires_at": None})
            == TOKEN_CACHE_TTL_SECONDS
        )

    def test_is_cut_short_at_the_token_expiry(self):
        with patch("courtlistener.mcp.auth.time") as clock:
            clock.time.return_value = 1_000
            assert cache_ttl({"user_hash": "h", "expires_at": 1_030}) == 30

    def test_never_drops_below_a_second(self):
        with patch("courtlistener.mcp.auth.time") as clock:
            clock.time.return_value = 1_000
            assert cache_ttl({"user_hash": "h", "expires_at": 900}) == 1


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
        with patch("courtlistener.mcp.auth.introspect_token", new=verify):
            info = run(resolve_token("tok", kind=TokenKind.OAUTH))
        assert info == {
            "user_hash": "uh",
            "kind": TokenKind.OAUTH,
            "cached": False,
        }
        assert run(get_session().get_token_info("tok", TokenKind.OAUTH)) == {
            "user_hash": "uh"
        }

    def test_kind_and_cached_are_not_persisted(self):
        """``kind`` already lives in the cache key, and ``cached`` is
        per-request state for the middleware — neither belongs in the
        stored record."""
        verify = AsyncMock(return_value={"user_hash": "uh"})
        with patch("courtlistener.mcp.auth.introspect_token", new=verify):
            run(resolve_token("tok", kind=TokenKind.OAUTH))
        stored = run(get_session().get_token_info("tok", TokenKind.OAUTH))
        assert stored == {"user_hash": "uh"}

    def test_scopes_and_expiry_are_persisted(self):
        info = {
            "user_hash": "uh",
            "scopes": ["openid", "api"],
            "expires_at": int(time.time()) + 3600,
        }
        with patch(
            "courtlistener.mcp.auth.introspect_token",
            new=AsyncMock(return_value=info),
        ):
            run(resolve_token("tok", kind=TokenKind.OAUTH))
        assert (
            run(get_session().get_token_info("tok", TokenKind.OAUTH)) == info
        )

    def test_cache_lifetime_follows_the_token_expiry(self):
        session = MagicMock(
            get_token_info=AsyncMock(return_value=None),
            store_token_info=AsyncMock(),
        )
        info = {"user_hash": "uh", "expires_at": 1_030}
        with (
            patch("courtlistener.mcp.auth.get_session", return_value=session),
            patch(
                "courtlistener.mcp.auth.introspect_token",
                new=AsyncMock(return_value=info),
            ),
            patch("courtlistener.mcp.auth.time") as clock,
        ):
            clock.time.return_value = 1_000
            run(resolve_token("tok", kind=TokenKind.OAUTH))
        session.store_token_info.assert_awaited_once_with(
            "tok", TokenKind.OAUTH, info, 30
        )

    def test_cache_hit_skips_verification(self):
        verify = AsyncMock(return_value={"user_hash": "uh"})
        with patch("courtlistener.mcp.auth.introspect_token", new=verify):
            run(resolve_token("tok", kind=TokenKind.OAUTH))
            info = run(resolve_token("tok", kind=TokenKind.OAUTH))
        assert verify.await_count == 1
        assert info["cached"] is True
        assert info["user_hash"] == "uh"

    def test_a_cached_entry_does_not_cross_credential_kinds(self):
        """The kind is part of the cache key, so an entry verified as
        one kind can't satisfy a lookup for another. Without that, a
        warm entry would let a credential in under the wrong scheme."""
        verify_oauth = AsyncMock(return_value={"user_hash": "uh"})
        verify_api = AsyncMock(return_value=None)
        with (
            patch("courtlistener.mcp.auth.introspect_token", new=verify_oauth),
            patch("courtlistener.mcp.auth.verify_api_token", new=verify_api),
        ):
            run(resolve_token("tok", kind=TokenKind.OAUTH))
            assert run(resolve_token("tok", kind=TokenKind.API)) is None
        # The OAuth entry was not served; the API kind had to go verify
        # for itself, and got nothing.
        verify_api.assert_awaited_once_with("tok")

    def test_api_kind_dispatches_to_the_api_verifier(self):
        verify_oauth = AsyncMock(return_value={"user_hash": "oauth-uh"})
        verify_api = AsyncMock(return_value={"user_hash": "api-uh"})
        with (
            patch("courtlistener.mcp.auth.introspect_token", new=verify_oauth),
            patch("courtlistener.mcp.auth.verify_api_token", new=verify_api),
        ):
            info = run(resolve_token("tok", kind=TokenKind.API))
        assert info == {
            "user_hash": "api-uh",
            "kind": TokenKind.API,
            "cached": False,
        }
        verify_oauth.assert_not_awaited()
        assert run(get_session().get_token_info("tok", TokenKind.API)) == {
            "user_hash": "api-uh"
        }

    @pytest.mark.parametrize("kind", list(TokenKind))
    def test_every_declared_kind_is_dispatched(self, kind):
        """Adding a ``TokenKind`` without a verifier branch is a mypy
        error at ``_assert_unhandled_token_kind``, but that only helps
        where mypy runs. At runtime every declared kind must still
        resolve through its own verifier — never fall through to
        another's, and never raise its way out as a 500.
        """
        verifiers = {
            TokenKind.OAUTH: "courtlistener.mcp.auth.introspect_token",
            TokenKind.API: "courtlistener.mcp.auth.verify_api_token",
        }
        assert kind in verifiers, f"no verifier wired for {kind}"
        with patch(
            verifiers[kind], new=AsyncMock(return_value={"user_hash": "uh"})
        ):
            info = run(resolve_token("tok", kind=kind))
        assert info is not None
        assert info["user_hash"] == "uh"
        assert info["kind"] == kind

    def test_failed_verification_is_not_cached(self):
        with patch(
            "courtlistener.mcp.auth.introspect_token",
            new=AsyncMock(return_value=None),
        ):
            assert run(resolve_token("tok", kind=TokenKind.OAUTH)) is None
        assert (
            run(get_session().get_token_info("tok", TokenKind.OAUTH)) is None
        )

    def test_session_store_outage_degrades_to_direct_verification(self):
        """A session-store outage must not turn every request into a
        500. The degradation lives in the Redis backend — connection
        failures read as misses and skip writes — so ``resolve_token``
        itself carries no guards and verification runs uncached."""
        down = RedisConnectionError("redis down")
        session = RedisSession("redis://example.test:6379")
        session._client = MagicMock(
            get=AsyncMock(side_effect=down),
            set=AsyncMock(side_effect=down),
        )
        set_session(session)
        with patch(
            "courtlistener.mcp.auth.introspect_token",
            new=AsyncMock(return_value={"user_hash": "uh"}),
        ):
            info = run(resolve_token("tok", kind=TokenKind.OAUTH))
        assert info is not None
        assert info["user_hash"] == "uh"
        assert info["cached"] is False


def _proxy(storage=None):
    """The authorization server ``create_http_app`` attaches, built for tests."""
    return CourtListenerOAuthProxy(
        upstream_authorization_endpoint="https://cl.example.test/o/authorize/",
        upstream_token_endpoint="https://cl.example.test/o/token/",
        upstream_revocation_endpoint="https://cl.example.test/o/revoke_token/",
        upstream_client_id="mcp-app",
        upstream_client_secret="s3cret",
        token_verifier=CourtListenerTokenVerifier(
            base_url="https://mcp.example.test"
        ),
        upstream_scopes=["openid", "api", "wiki", "email"],
        upstream_resources=[
            "https://cl.example.test/api/rest/v4/",
            "https://wiki.example.test",
        ],
        base_url="https://mcp.example.test",
        client_storage=storage or MemoryStore(),
        jwt_signing_key=b"0" * 32,
    )


class TestServerAuthWiring:
    """The HTTP factory always attaches the OAuth proxy — there is no
    auth-off HTTP mode — while ``create_mcp_server`` itself stays
    auth-free so stdio remains credential-free."""

    def test_http_app_always_authenticates(self):
        """Regression guard for the removed ``MCP_REQUIRE_OAUTH`` flag,
        which fail-opened: any value other than exactly "true" silently
        deployed an unauthenticated server. The factory now wires auth
        with no conditional at all, and the setting itself is gone."""
        import courtlistener.mcp.server as server_mod
        import courtlistener.mcp.settings as settings_mod

        assert not hasattr(settings_mod, "MCP_REQUIRE_OAUTH")
        with (
            patch.dict("os.environ", {"MCP_REQUIRE_OAUTH": "false"}),
            patch.object(server_mod, "REDIS_URL", "redis://localhost:6379"),
            patch.object(server_mod, "OAUTH_CLIENT_ID", "mcp-app"),
            patch.object(server_mod, "OAUTH_CLIENT_SECRET", "s3cret"),
            patch.object(server_mod, "build_client_storage", MemoryStore),
        ):
            app = server_mod.create_http_app()
        assert AuthenticationMiddleware in [
            mw.cls for mw in app.user_middleware
        ]

    def test_http_mode_requires_the_upstream_client(self):
        import courtlistener.mcp.server as server_mod

        with (
            patch.object(server_mod, "REDIS_URL", "redis://localhost:6379"),
            patch.object(server_mod, "OAUTH_CLIENT_ID", None),
            pytest.raises(ValueError, match="COURTLISTENER_OAUTH_CLIENT_ID"),
        ):
            server_mod.create_http_app()

    def test_verifier_requires_the_api_scope(self):
        """``api`` is what CL's REST API expects downstream; it is the
        one scope every request must carry, and the one API tokens are
        credited with."""
        verifier = CourtListenerTokenVerifier(
            base_url="https://mcp.example.test"
        )
        assert verifier.required_scopes == ["api"]

    def test_verifier_accepts_a_resolved_token(self):
        """Successful resolution → AccessToken carrying the user_hash
        and the credential kind in its claims, plus the scopes and
        expiry CourtListener reported."""
        verifier = CourtListenerTokenVerifier(
            base_url="https://mcp.example.test"
        )
        with patch(
            "courtlistener.mcp.auth.resolve_token",
            new=AsyncMock(
                return_value={
                    "user_hash": "fake-user-hash",
                    "scopes": ["openid", "api", "wiki", "email"],
                    "expires_at": 1_900_000_000,
                    "kind": TokenKind.OAUTH,
                    "cached": False,
                }
            ),
        ):
            token = run(verifier.verify_token("anything-goes"))
        assert token is not None
        assert token.token == "anything-goes"
        assert token.claims.get("user_hash") == "fake-user-hash"
        assert token.claims.get("token_kind") == TokenKind.OAUTH
        assert token.claims.get("cached") is False
        assert token.scopes == ["openid", "api", "wiki", "email"]
        assert token.expires_at == 1_900_000_000

    def test_verifier_credits_api_tokens_with_the_required_scopes(self):
        verifier = CourtListenerTokenVerifier(
            base_url="https://mcp.example.test"
        )
        with patch(
            "courtlistener.mcp.auth.resolve_token",
            new=AsyncMock(
                return_value={
                    "user_hash": "h",
                    "kind": TokenKind.API,
                    "cached": False,
                }
            ),
        ):
            token = run(verifier.verify_token("cl-api-token", TokenKind.API))
        assert token is not None
        assert token.scopes == ["api"]
        assert token.expires_at is None

    def test_verifier_asks_for_an_oauth_credential(self):
        """The proxy calls the bare ``verify_token`` contract for the
        CourtListener token behind each JWT, so OAuth is the default."""
        verifier = CourtListenerTokenVerifier(
            base_url="https://mcp.example.test"
        )
        resolve = AsyncMock(
            return_value={
                "user_hash": "h",
                "kind": TokenKind.OAUTH,
                "cached": False,
            }
        )
        with patch("courtlistener.mcp.auth.resolve_token", new=resolve):
            run(verifier.verify_token("cl-token"))
        resolve.assert_awaited_once_with("cl-token", kind=TokenKind.OAUTH)

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
                    "kind": TokenKind.OAUTH,
                    "cached": True,
                }
            ),
        ):
            token = run(verifier.verify_token("cached-token"))
        assert token is not None
        assert token.claims.get("cached") is True

    def test_verifier_rejects_an_unresolvable_token(self):
        """Resolution returning ``None`` (inactive/non-200/network error)
        → ``verify_token`` returns ``None``, which the proxy turns into
        a 401 with ``WWW-Authenticate`` so the MCP client re-runs OAuth.
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
        """Empty token → short-circuit without touching the cache or
        CourtListener."""
        verifier = CourtListenerTokenVerifier(
            base_url="https://mcp.example.test"
        )
        resolve = AsyncMock()
        with patch("courtlistener.mcp.auth.resolve_token", new=resolve):
            assert run(verifier.verify_token("")) is None
        resolve.assert_not_awaited()

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
        """A backend over verifiers that record how they were asked."""
        bearer = MagicMock(verify_token=AsyncMock(return_value=oauth))
        api_verifier = MagicMock(verify_token=AsyncMock(return_value=api))
        return (
            CourtListenerAuthBackend(bearer, api_verifier),
            bearer,
            api_verifier,
        )

    def _accepted(self):
        token = MagicMock()
        token.scopes = ["api"]
        token.expires_at = None
        token.client_id = "courtlistener-mcp"
        return token

    def test_token_scheme_verifies_as_an_api_credential(self):
        backend, bearer, api = self._backend(api=self._accepted())
        result = run(backend.authenticate(self._conn("Token cl-api-token")))
        assert result is not None
        api.verify_token.assert_awaited_once_with(
            "cl-api-token", TokenKind.API
        )
        bearer.verify_token.assert_not_awaited()

    def test_bearer_scheme_stays_on_the_sdk_path(self):
        """Bearer is handed to the parent, whose verifier is the OAuth
        proxy itself: the SDK asks via the bare ``verify_token``
        contract and the proxy swaps the JWT for the upstream token."""
        backend, bearer, api = self._backend(oauth=self._accepted())
        result = run(backend.authenticate(self._conn("Bearer mcp-jwt")))
        assert result is not None
        bearer.verify_token.assert_awaited_once_with("mcp-jwt")
        api.verify_token.assert_not_awaited()

    def test_scheme_match_is_case_insensitive(self):
        """RFC 7235 credential schemes are case-insensitive, and clients
        do vary (``token`` vs ``Token``)."""
        backend, _, api = self._backend(api=self._accepted())
        run(backend.authenticate(self._conn("token cl-api-token")))
        api.verify_token.assert_awaited_once_with(
            "cl-api-token", TokenKind.API
        )

    def test_rejected_api_token_yields_no_user(self):
        backend, _, _ = self._backend(api=None)
        assert run(backend.authenticate(self._conn("Token nope"))) is None

    def test_expired_api_token_is_rejected(self):
        expired = self._accepted()
        expired.expires_at = 1
        backend, _, _ = self._backend(api=expired)
        assert run(backend.authenticate(self._conn("Token old"))) is None

    def test_unsupported_scheme_is_rejected(self):
        backend, bearer, api = self._backend(api=self._accepted())
        assert run(backend.authenticate(self._conn("Basic abc123"))) is None
        bearer.verify_token.assert_not_awaited()
        api.verify_token.assert_not_awaited()

    def test_missing_header_is_rejected(self):
        backend, bearer, api = self._backend(api=self._accepted())
        assert run(backend.authenticate(self._conn(None))) is None
        bearer.verify_token.assert_not_awaited()
        api.verify_token.assert_not_awaited()

    def test_empty_credential_costs_no_round_trip(self):
        backend, bearer, api = self._backend(api=self._accepted())
        assert run(backend.authenticate(self._conn("Token "))) is None
        bearer.verify_token.assert_not_awaited()
        api.verify_token.assert_not_awaited()


def _http(proxy):
    """A test client over the HTTP app with *proxy* attached."""
    from starlette.testclient import TestClient

    from courtlistener.mcp.server import create_mcp_server

    return TestClient(create_mcp_server(auth=proxy).http_app(path="/"))


def _mint_access_token(proxy, upstream_token="cl-token"):
    """A JWT the proxy would have issued, pointing at a stored CL token."""
    from fastmcp.server.auth.oauth_proxy.models import (
        JTIMapping,
        UpstreamTokenSet,
    )

    now = time.time()

    async def seed():
        await proxy._upstream_token_store.put(
            key="upstream-1",
            value=UpstreamTokenSet(
                upstream_token_id="upstream-1",
                access_token=upstream_token,
                refresh_token=None,
                refresh_token_expires_at=None,
                expires_at=now + 3600,
                token_type="Bearer",
                scope="openid api wiki email",
                client_id="client-1",
                created_at=now,
            ),
            ttl=3600,
        )
        await proxy._jti_mapping_store.put(
            key="jti-1",
            value=JTIMapping(
                jti="jti-1", upstream_token_id="upstream-1", created_at=now
            ),
            ttl=3600,
        )

    run(seed())
    return proxy.jwt_issuer.issue_access_token(
        client_id="client-1",
        scopes=["openid", "api", "wiki", "email"],
        jti="jti-1",
        expires_in=3600,
    )


class TestCourtListenerOAuthProxy:
    """The proxy is the authorization server MCP clients see. It brokers
    the CourtListener login with the server's own application, asks for
    a fixed scope set and resource indicators regardless of what the
    client requested, and swaps CL tokens for its own JWTs."""

    def test_installs_the_dual_scheme_backend(self):
        proxy = _proxy()
        auth_mw = proxy.get_middleware()[0]
        assert auth_mw.cls is AuthenticationMiddleware
        backend = auth_mw.kwargs["backend"]
        assert isinstance(backend, CourtListenerAuthBackend)
        assert backend.token_verifier is proxy
        assert backend.api_verifier is proxy.api_verifier

    def test_serves_the_authorization_server_and_resource_metadata(self):
        paths = {route.path for route in _proxy().get_routes(mcp_path="/")}
        assert {
            "/.well-known/oauth-authorization-server",
            "/.well-known/openid-configuration",
            "/.well-known/oauth-protected-resource",
            "/authorize",
            "/token",
            "/register",
            "/revoke",
            "/auth/callback",
        } <= paths

    def test_metadata_names_the_proxy_as_the_authorization_server(self):
        with _http(_proxy()) as http:
            resource = http.get("/.well-known/oauth-protected-resource").json()
            server = http.get("/.well-known/oauth-authorization-server").json()
            alias = http.get("/.well-known/openid-configuration").json()
        assert resource["authorization_servers"] == [
            "https://mcp.example.test/"
        ]
        assert server["issuer"] == "https://mcp.example.test/"
        assert server["scopes_supported"] == ["openid", "api", "wiki", "email"]
        assert resource["scopes_supported"] == server["scopes_supported"]
        assert alias == server

    def test_asks_courtlistener_for_the_fixed_scopes_and_no_client_resource(
        self,
    ):
        url = _proxy()._build_upstream_authorize_url(
            "txn-1",
            {
                "scopes": ["openid", "api"],
                "resource": "https://mcp.example.test/",
                "proxy_code_verifier": "v" * 48,
            },
        )
        query = parse_qs(urlparse(url).query)
        assert url.startswith("https://cl.example.test/o/authorize/?")
        assert query["client_id"] == ["mcp-app"]
        assert query["redirect_uri"] == [
            "https://mcp.example.test/auth/callback"
        ]
        assert query["state"] == ["txn-1"]
        assert query["scope"] == ["openid api wiki email"]
        assert query["code_challenge_method"] == ["S256"]
        assert "resource" not in query

    def test_code_exchange_sends_no_scope(self):
        assert _proxy()._prepare_scopes_for_token_exchange(["api"]) == []

    def test_upstream_token_requests_carry_the_resource_indicators(self):
        sent = []

        def record(request):
            sent.append(request.content.decode())
            return httpx.Response(200, json={"access_token": "t"})

        client = ResourceIndicatorClient(
            resources=[
                "https://cl.example.test/api/rest/v4/",
                "https://w.test",
            ],
            client_id="mcp-app",
            client_secret="s3cret",
            transport=httpx.MockTransport(record),
        )
        run(
            client.post(
                "https://cl.example.test/o/token/",
                data={"grant_type": "authorization_code", "code": "c"},
                auth=None,
            )
        )
        run(
            client.post(
                "https://cl.example.test/x", data={"token": "t"}, auth=None
            )
        )
        assert (
            "resource=https%3A%2F%2Fcl.example.test%2Fapi%2Frest%2Fv4%2F"
            "&resource=https%3A%2F%2Fw.test"
        ) in sent[0]
        assert "resource" not in sent[1]

    def test_proxy_builds_its_upstream_client_with_the_resources(self):
        proxy = _proxy()
        client = proxy._create_upstream_oauth_client()
        assert isinstance(client, ResourceIndicatorClient)
        assert client.resources == proxy.upstream_resources
        assert client.client_id == "mcp-app"

    def test_token_endpoint_accepts_basic_auth_without_client_id_in_body(
        self,
    ):
        """RFC 6749 §2.3.1 clients put the credentials only in the
        ``Authorization`` header; the SDK alone rejects that with
        ``invalid_client``. Here the request gets past client
        authentication and fails on the (bogus) code instead."""
        with _http(_proxy()) as http:
            registered = http.post(
                "/register",
                json={
                    "redirect_uris": ["http://127.0.0.1:1/cb"],
                    "token_endpoint_auth_method": "client_secret_basic",
                },
            ).json()
            credentials = base64.b64encode(
                f"{registered['client_id']}:{registered['client_secret']}".encode()
            ).decode()
            response = http.post(
                "/token",
                data={
                    "grant_type": "authorization_code",
                    "code": "nope",
                    "redirect_uri": "http://127.0.0.1:1/cb",
                    "code_verifier": "v" * 43,
                },
                headers={"Authorization": f"Basic {credentials}"},
            )
        assert response.status_code == 401
        assert response.json()["error"] == "invalid_grant"


class TestAuthOverHttp:
    """End to end through FastMCP's middleware stack: the scheme has to
    survive the whole chain, not just our backend in isolation."""

    @pytest.fixture(autouse=True)
    def fresh_session(self):
        set_session(InMemorySession())
        yield
        set_session(None)

    @pytest.fixture
    def proxy(self):
        return _proxy()

    def _initialize(self, proxy, headers):
        with _http(proxy) as http:
            return http.post(
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
        info = {
            "user_hash": "uh",
            "scopes": ["openid", "api", "wiki", "email"],
        }
        return (
            patch(
                "courtlistener.mcp.auth.introspect_token",
                new=AsyncMock(return_value=info if oauth_ok else None),
            ),
            patch(
                "courtlistener.mcp.auth.verify_api_token",
                new=AsyncMock(
                    return_value={"user_hash": "uh"} if api_ok else None
                ),
            ),
        )

    def test_api_token_is_accepted(self, proxy):
        oauth_patch, api_patch = self._patch_verifiers(
            oauth_ok=False, api_ok=True
        )
        with oauth_patch, api_patch:
            resp = self._initialize(
                proxy, {"Authorization": "Token cl-api-token"}
            )
        assert resp.status_code == 200

    def test_oauth_bearer_is_accepted(self, proxy):
        """A JWT the proxy issued is swapped for the CourtListener token
        behind it, and that token is what gets introspected."""
        with _http(proxy):
            jwt = _mint_access_token(proxy)
        oauth_patch, api_patch = self._patch_verifiers(
            oauth_ok=True, api_ok=False
        )
        with oauth_patch as introspect, api_patch:
            resp = self._initialize(proxy, {"Authorization": f"Bearer {jwt}"})
        assert resp.status_code == 200
        introspect.assert_awaited_once_with("cl-token")

    def test_revoked_upstream_token_is_rejected(self, proxy):
        with _http(proxy):
            jwt = _mint_access_token(proxy)
        oauth_patch, api_patch = self._patch_verifiers(
            oauth_ok=False, api_ok=False
        )
        with oauth_patch, api_patch:
            resp = self._initialize(proxy, {"Authorization": f"Bearer {jwt}"})
        assert resp.status_code == 401

    def test_courtlistener_tokens_are_not_accepted_directly(self, proxy):
        """Only the proxy's own JWTs are bearer credentials: a token
        CourtListener issued to some other client is rejected even when
        CourtListener would vouch for it."""
        oauth_patch, api_patch = self._patch_verifiers(
            oauth_ok=True, api_ok=True
        )
        with oauth_patch, api_patch:
            resp = self._initialize(
                proxy, {"Authorization": "Bearer cl-token"}
            )
        assert resp.status_code == 401
        assert "resource_metadata=" in resp.headers["www-authenticate"]

    def test_oauth_token_sent_as_token_scheme_is_rejected(self, proxy):
        """The other inversion: a ``Token`` credential is only ever
        checked against CL's API."""
        with _http(proxy):
            jwt = _mint_access_token(proxy)
        oauth_patch, api_patch = self._patch_verifiers(
            oauth_ok=True, api_ok=False
        )
        with oauth_patch, api_patch:
            resp = self._initialize(proxy, {"Authorization": f"Token {jwt}"})
        assert resp.status_code == 401

    def test_missing_credentials_still_get_the_oauth_challenge(self, proxy):
        """Unauthenticated requests must keep advertising Bearer so
        OAuth discovery is untouched — ``Token`` support is deliberately
        not advertised in the RFC 6750 methods."""
        resp = self._initialize(proxy, {})
        assert resp.status_code == 401
        assert resp.headers["www-authenticate"].startswith("Bearer")


class TestHealthEndpoint:
    """``/health`` must stay unauthenticated so uptime checks keep
    working even when OAuth is enabled on the MCP routes."""

    def test_health_is_unauthenticated_under_oauth(self):
        with _http(_proxy()) as http:
            response = http.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"
        assert body["services"] == {"mcp": True}


class TestOpenAIAppsChallenge:
    """The OpenAI Apps domain-verification challenge must be served
    publicly (unauthenticated) so OpenAI can fetch it even when OAuth is
    enabled on the MCP routes."""

    def test_challenge_is_unauthenticated_under_oauth(self):
        from courtlistener.mcp.settings import OPENAI_APPS_CHALLENGE_TOKEN

        with _http(_proxy()) as http:
            response = http.get("/.well-known/openai-apps-challenge")
        assert response.status_code == 200
        assert response.text == OPENAI_APPS_CHALLENGE_TOKEN
        assert response.headers["content-type"].startswith("text/plain")
