from enum import Enum
from typing import TypedDict

from typing_extensions import NotRequired


class TokenKind(str, Enum):
    """A kind of credential the server knows how to verify."""

    OAUTH = "oauth"
    API = "api_token"

    # Not cosmetic: used as token info cache key suffix.
    __str__ = str.__str__

    @property
    def scheme(self) -> str:
        """The ``Authorization`` scheme this kind arrives under."""
        return TOKEN_KIND_SCHEMES[self]

    @classmethod
    def from_scheme(cls, scheme: str) -> "TokenKind | None":
        """Return the kind for an ``Authorization`` scheme, or ``None``."""
        scheme = scheme.lower()
        return next((kind for kind in cls if kind.scheme == scheme), None)


TOKEN_KIND_SCHEMES = {
    TokenKind.OAUTH: "bearer",
    TokenKind.API: "token",
}


# The client id of a session with no OAuth client (API token sessions).
NO_CLIENT_ID = "courtlistener-mcp"

# The client id of an OAuth session whose client could not be determined.
UNKNOWN_CLIENT_ID = "unknown-oauth-client"


class TokenInfo(TypedDict):
    """A verified credential, as persisted in the session store."""

    user_hash: str
    client_id: NotRequired[str | None]
    scopes: NotRequired[list[str]]
    expires_at: NotRequired[int | None]
