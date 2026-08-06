from __future__ import annotations

from functools import cached_property
from typing import Any

from fastmcp.server.context import Context
from fastmcp.server.dependencies import get_access_token, get_http_request
from fastmcp.tools import Tool
from jsonschema import Draft202012Validator
from mcp.types import ToolAnnotations

from courtlistener import CourtListener
from courtlistener.mcp.auth_types import TokenKind
from courtlistener.mcp.exceptions import ToolArgumentValidationError


class MCPTool:
    name: str | None = None
    annotations: ToolAnnotations | None = None

    def get_client(self) -> CourtListener:
        """Build a CourtListener client for the current request.

        Resolution order:
        1. HTTP + auth mode: the credential FastMCP verified. Its
           ``token_kind`` claim says which scheme CL expects it back
           under — an OAuth access token as ``Authorization: Bearer
           <jwt>`` (accepted because ``OAuth2Authentication`` is
           registered in CL's ``DEFAULT_AUTHENTICATION_CLASSES``), or a
           CL API token as ``Authorization: Token <api_token>``. Sending
           either under the other scheme is rejected by CL.
        2. HTTP + auth disabled: ``Authorization: Token <api_token>``
           header (existing stdio-over-HTTP / testing path). Reachable
           only while ``MCP_REQUIRE_OAUTH`` can turn the auth provider
           off; with it on, the auth layer consumes the header first.
        3. stdio mode: ``COURTLISTENER_API_TOKEN`` env var, resolved
           by the ``CourtListener`` constructor.
        """
        # 1. Verified credential (HTTP + auth provider active)
        access_token = get_access_token()
        if access_token is not None:
            if access_token.claims.get("token_kind") == TokenKind.API:
                return CourtListener(api_token=access_token.token)
            return CourtListener(access_token=access_token.token)

        # 2. "Token ..." header pass-through (auth provider off).
        #    get_http_request() raises when called outside an HTTP
        #    request (e.g. stdio mode), so guard against that.
        try:
            request = get_http_request()
        except RuntimeError:
            request = None
        if request is not None:
            auth = request.headers.get("Authorization")
            if auth and auth.startswith("Token "):
                return CourtListener(api_token=auth[len("Token ") :] or None)

        # 3. stdio mode — env var
        return CourtListener()

    def get_tool(self) -> Tool:
        if self.name is None:
            raise ValueError("name must be set")
        if self.annotations is None:
            raise ValueError("annotations must be set")
        return Tool(
            name=self.name,
            description=self.get_description(),
            parameters=self.get_input_schema(),
            annotations=self.annotations,
        )

    def get_description(self) -> str:
        return self.__doc__ or ""

    def get_input_schema(self) -> dict:
        raise NotImplementedError(
            "get_input_schema must be implemented by subclass"
        )

    @cached_property
    def input_schema(self) -> dict:
        """Cached input schema for the tool."""
        return self.get_input_schema()

    @cached_property
    def input_validator(self) -> Draft202012Validator:
        """Cached validator for the tool's input schema."""
        return Draft202012Validator(self.input_schema)

    def validate_arguments(self, arguments: dict) -> None:
        """Check arguments against the tool's input schema."""
        if self.name is None:
            raise ValueError("name must be set")
        arguments = {
            key: value for key, value in arguments.items() if value is not None
        }
        errors = sorted(
            self.input_validator.iter_errors(arguments),
            key=lambda error: list(error.path),
        )
        if not errors:
            return

        messages = []
        argument_names: set[str] = set()
        for error in errors:
            location = ".".join(str(part) for part in error.path)
            prefix = f"{location}: " if location else ""
            messages.append(f"{prefix}{error.message}")
            if error.path:
                argument_names.add(str(error.path[0]))
            elif error.validator == "additionalProperties":
                known = self.input_schema.get("properties", {})
                argument_names.update(
                    key for key in arguments if key not in known
                )
            elif error.validator == "required":
                argument_names.update(
                    key
                    for key in error.validator_value
                    if key not in arguments
                )
            else:
                argument_names.add("__root__")
        raise ToolArgumentValidationError(
            f"Invalid arguments for tool '{self.name}':\n- "
            + "\n- ".join(messages),
            tool_name=self.name,
            argument_names=sorted(argument_names),
        )

    async def __call__(self, arguments: dict, ctx: Context) -> Any:
        raise NotImplementedError("__call__ must be implemented by subclass")
