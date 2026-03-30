"""Tests for auth middleware and token resolution."""

from __future__ import annotations

import contextvars
from unittest.mock import patch

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from courtlistener.mcp.auth import (
    AuthMiddleware,
    request_api_token,
)
from courtlistener.mcp.tools.mcp_tool import MCPTool


def _make_app():
    """Create a minimal Starlette app that echoes the ContextVar
    value back in the response, wrapped with AuthMiddleware."""

    async def echo_token(request: Request) -> JSONResponse:
        token = request_api_token.get()
        return JSONResponse({"token": token})

    app = Starlette(
        routes=[Route("/echo", echo_token)],
    )
    return AuthMiddleware(app)


class TestAuthMiddleware:
    def setup_method(self):
        self.app = _make_app()
        self.client = TestClient(self.app)

    def test_extracts_token_from_header(self):
        """Authorization: Token <value> -> ContextVar set."""
        resp = self.client.get(
            "/echo",
            headers={"Authorization": "Token my-secret-token"},
        )
        assert resp.status_code == 200
        assert resp.json()["token"] == "my-secret-token"

    def test_bearer_scheme_ignored(self):
        """Bearer scheme is not Token scheme -> None."""
        resp = self.client.get(
            "/echo",
            headers={"Authorization": "Bearer some-jwt"},
        )
        assert resp.status_code == 200
        assert resp.json()["token"] is None

    def test_missing_authorization_header(self):
        """No Authorization header -> None."""
        resp = self.client.get("/echo")
        assert resp.status_code == 200
        assert resp.json()["token"] is None

    def test_empty_authorization_header(self):
        """Empty Authorization header -> None."""
        resp = self.client.get(
            "/echo",
            headers={"Authorization": ""},
        )
        assert resp.status_code == 200
        assert resp.json()["token"] is None

    def test_contextvar_reset_between_requests(self):
        """Token from request 1 must not leak into request 2."""
        resp1 = self.client.get(
            "/echo",
            headers={"Authorization": "Token first-token"},
        )
        assert resp1.json()["token"] == "first-token"

        resp2 = self.client.get("/echo")
        assert resp2.json()["token"] is None

    def test_token_with_special_characters(self):
        """Tokens may contain various characters."""
        token = "abc123-def_456.xyz"
        resp = self.client.get(
            "/echo",
            headers={"Authorization": f"Token {token}"},
        )
        assert resp.json()["token"] == token

    def test_token_prefix_only(self):
        """'Token ' with no value -> normalized to None."""
        resp = self.client.get(
            "/echo",
            headers={"Authorization": "Token "},
        )
        assert resp.json()["token"] is None


class TestGetClient:
    def setup_method(self):
        self.tool = MCPTool()

    def test_with_contextvar_token(self):
        """When ContextVar has a token, pass it to CourtListener."""
        reset = request_api_token.set("test-token")
        try:
            with patch(
                "courtlistener.mcp.tools.mcp_tool.CourtListener"
            ) as mock_cl:
                self.tool.get_client()
                mock_cl.assert_called_once_with(api_token="test-token")
        finally:
            request_api_token.reset(reset)

    def test_without_contextvar_falls_back(self):
        """When ContextVar is None, call CourtListener() with no args
        (env var fallback)."""
        reset = request_api_token.set(None)
        try:
            with patch(
                "courtlistener.mcp.tools.mcp_tool.CourtListener"
            ) as mock_cl:
                self.tool.get_client()
                mock_cl.assert_called_once_with()
        finally:
            request_api_token.reset(reset)

    def test_default_contextvar_falls_back(self):
        """When ContextVar is at default (never set), call
        CourtListener() with no args."""
        ctx = contextvars.copy_context()

        def run():
            with patch(
                "courtlistener.mcp.tools.mcp_tool.CourtListener"
            ) as mock_cl:
                self.tool.get_client()
                mock_cl.assert_called_once_with()

        ctx.run(run)


class TestGetUserId:
    def setup_method(self):
        self.tool = MCPTool()

    def test_with_token_returns_hash(self):
        """With a token, returns a 16-char hex hash."""
        reset = request_api_token.set("my-api-token")
        try:
            user_id = self.tool.get_user_id()
            assert len(user_id) == 16
            assert all(c in "0123456789abcdef" for c in user_id)
        finally:
            request_api_token.reset(reset)

    def test_with_token_is_deterministic(self):
        """Same token -> same user_id."""
        reset = request_api_token.set("my-api-token")
        try:
            id1 = self.tool.get_user_id()
            id2 = self.tool.get_user_id()
            assert id1 == id2
        finally:
            request_api_token.reset(reset)

    def test_different_tokens_different_ids(self):
        """Different tokens produce different user_ids."""
        reset = request_api_token.set("token-a")
        try:
            id_a = self.tool.get_user_id()
        finally:
            request_api_token.reset(reset)

        reset = request_api_token.set("token-b")
        try:
            id_b = self.tool.get_user_id()
        finally:
            request_api_token.reset(reset)

        assert id_a != id_b

    def test_without_token_returns_local(self):
        """Without a token (stdio mode), returns 'local'."""
        reset = request_api_token.set(None)
        try:
            assert self.tool.get_user_id() == "local"
        finally:
            request_api_token.reset(reset)
