from __future__ import annotations

import contextvars

from starlette.types import ASGIApp, Receive, Scope, Send

request_api_token: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_api_token", default=None
)


class AuthMiddleware:
    """ASGI middleware that extracts the API token from the
    Authorization header.

    Reads ``Authorization: Token <value>`` and stores the token in
    the ``request_api_token`` ContextVar for the duration of the
    request. Does **not** reject missing or malformed headers —
    authentication errors surface downstream when the CourtListener
    API rejects the call.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] in ("http", "websocket"):
            headers = dict(scope.get("headers", []))
            auth = headers.get(b"authorization", b"").decode()
            token = None
            if auth.startswith("Token "):
                token = auth[len("Token ") :] or None
            reset = request_api_token.set(token)
            try:
                await self.app(scope, receive, send)
            finally:
                request_api_token.reset(reset)
        else:
            await self.app(scope, receive, send)
