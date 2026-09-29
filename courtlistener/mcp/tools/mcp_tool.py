from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from functools import cached_property
from typing import Any, ClassVar

import httpx
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token
from fastmcp.tools import Tool, ToolResult
from jsonschema import Draft202012Validator
from mcp.types import TextContent, ToolAnnotations
from pydantic import Field

from courtlistener import AsyncCourtListener
from courtlistener.exceptions import CourtListenerAPIError, InvalidFieldsError
from courtlistener.mcp.auth_types import TokenKind
from courtlistener.mcp.exceptions import (
    SentryExemptToolError,
    ToolArgumentValidationError,
    UnauthorizedToolError,
    UpstreamCourtListenerError,
)
from courtlistener.mcp.metrics import error_outcome, tool_calls_total
from courtlistener.mcp.session import get_session, json_default


def schema_allows_type(schema: Mapping[str, Any], type_name: str) -> bool:
    """Whether *schema* or any of its union branches declares *type_name*."""
    declared = schema.get("type", [])
    if type_name in ([declared] if isinstance(declared, str) else declared):
        return True
    return any(
        schema_allows_type(branch, type_name)
        for key in ("anyOf", "oneOf")
        for branch in schema.get(key, [])
    )


def array_item_schemas(schema: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The ``items`` schemas of *schema* and its union branches."""
    items = schema.get("items")
    return ([items] if isinstance(items, Mapping) else []) + [
        item
        for key in ("anyOf", "oneOf")
        for branch in schema.get(key, [])
        for item in array_item_schemas(branch)
    ]


def coerce_integral_floats(value: Any, schema: Mapping[str, Any]) -> Any:
    """*value* with integral floats as ints where *schema* wants integers."""
    if isinstance(value, float):
        if (
            value.is_integer()
            and schema_allows_type(schema, "integer")
            and not schema_allows_type(schema, "number")
        ):
            return int(value)
    elif isinstance(value, list):
        items = {"anyOf": array_item_schemas(schema)}
        return [coerce_integral_floats(item, items) for item in value]
    return value


class MCPTool(Tool):
    """A FastMCP tool with a hand-written input schema and a CL client."""

    annotations: ToolAnnotations
    parameters: dict[str, Any] = Field(default_factory=dict)
    argument_aliases: ClassVar[dict[str, str]] = {}

    def model_post_init(self, context: Any, /) -> None:
        super().model_post_init(context)
        if self.description is None:
            self.description = type(self).__doc__ or ""
        if not self.parameters:
            self.parameters = self.get_input_schema()

    def get_input_schema(self) -> dict:
        raise NotImplementedError(
            "get_input_schema must be implemented by subclass"
        )

    async def call(self, arguments: dict) -> dict | str:
        """The tool body; ``run`` validates, translates errors, serializes."""
        raise NotImplementedError("call must be implemented by subclass")

    def get_client(self) -> AsyncCourtListener:
        """Build a CourtListener client for the current request.

        HTTP mode: the credential FastMCP verified. Its ``token_kind``
        claim says which scheme CL expects it back under — an OAuth
        access token as ``Authorization: Bearer <jwt>`` (accepted
        because ``OAuth2Authentication`` is registered in CL's
        ``DEFAULT_AUTHENTICATION_CLASSES``), or a CL API token as
        ``Authorization: Token <api_token>``. Sending either under the
        other scheme is rejected by CL.

        stdio mode: there is no HTTP layer, so no access token exists;
        the credential is the ``COURTLISTENER_API_TOKEN`` env var,
        resolved by the ``AsyncCourtListener`` constructor.
        """
        access_token = get_access_token()
        if access_token is not None:
            if access_token.claims.get("token_kind") == TokenKind.API:
                return AsyncCourtListener(api_token=access_token.token)
            return AsyncCourtListener(access_token=access_token.token)
        return AsyncCourtListener()

    @cached_property
    def input_validator(self) -> Draft202012Validator:
        """Cached validator for the tool's input schema."""
        return Draft202012Validator(self.parameters)

    @cached_property
    def property_validators(self) -> dict[str, Draft202012Validator]:
        """Cached validators for each top-level argument's schema."""
        return {
            name: Draft202012Validator(schema)
            for name, schema in self.parameters.get("properties", {}).items()
        }

    def decode_json_arguments(self, arguments: dict) -> dict:
        """Decode arguments that clients sent as JSON-encoded strings.

        Some clients send ``[1, 2]`` as ``"[1, 2]"`` or ``5`` as ``"5"``.
        """
        decoded = dict(arguments)
        for name, value in arguments.items():
            validator = self.property_validators.get(name)
            if validator is None or not isinstance(value, str):
                continue
            try:
                parsed = json.loads(value)
            except (ValueError, RecursionError):
                continue
            schema = self.parameters["properties"][name]
            parsed = coerce_integral_floats(parsed, schema)
            if isinstance(parsed, str) or not validator.is_valid(parsed):
                continue
            # Containers win even where the raw string is also valid
            # (e.g. `fields`); scalars only rescue an invalid string.
            if isinstance(parsed, list | dict) or not validator.is_valid(
                value
            ):
                decoded[name] = parsed
        return decoded

    def coerce_integral_float_arguments(self, arguments: dict) -> dict:
        """Turn ``5.0`` into ``5`` where the schema wants an integer."""
        properties = self.parameters.get("properties", {})
        return {
            name: coerce_integral_floats(value, properties[name])
            if name in properties
            else value
            for name, value in arguments.items()
        }

    def validate_arguments(self, arguments: dict) -> None:
        """Check arguments against the tool's input schema."""
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
                known = self.parameters.get("properties", {})
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

    def resolve_argument_aliases(self, arguments: dict) -> dict:
        """Rename aliased arguments to their canonical names."""
        resolved = dict(arguments)
        for alias, canonical in self.argument_aliases.items():
            if alias not in resolved:
                continue
            value = resolved.pop(alias)
            if value is None:
                continue
            existing = resolved.get(canonical)
            if existing is not None and existing != value:
                raise ToolArgumentValidationError(
                    f"Invalid arguments for tool '{self.name}':\n- "
                    f"`{alias}` is an alias for `{canonical}` and they "
                    f"differ; pass only `{canonical}`.",
                    tool_name=self.name,
                    argument_names=sorted([alias, canonical]),
                )
            resolved[canonical] = value
        return resolved

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        """FastMCP's entry point for a tool call."""
        try:
            result = await self._handle(arguments)
        except Exception as exc:
            tool_calls_total.labels(
                tool=self.name, outcome=error_outcome(exc)
            ).inc()
            raise
        tool_calls_total.labels(tool=self.name, outcome="ok").inc()
        return result

    async def _handle(self, arguments: dict[str, Any]) -> ToolResult:
        """Validate, call, translate errors, and serialize."""
        arguments = self.resolve_argument_aliases(arguments)
        arguments = self.decode_json_arguments(arguments)
        arguments = self.coerce_integral_float_arguments(arguments)
        self.validate_arguments(arguments)
        try:
            result = await self.call(arguments)
        except InvalidFieldsError as exc:
            raise ToolArgumentValidationError(
                str(exc), tool_name=self.name, argument_names=["fields"]
            ) from exc
        except CourtListenerAPIError as exc:
            error = await self.translate_api_error(exc)
            raise error from exc
        except httpx.HTTPError as exc:
            raise UpstreamCourtListenerError(
                f"Upstream CourtListener request failed: {exc}",
                tool_name=self.name,
                status="connection",
            ) from exc

        if isinstance(result, dict):
            result = json.dumps(result, default=json_default, indent=2)
        if not isinstance(result, str):
            raise ValueError(f"Invalid result type: {type(result)}")
        return ToolResult(content=[TextContent(type="text", text=result)])

    async def translate_api_error(
        self, exc: CourtListenerAPIError
    ) -> ToolError:
        """The ``ToolError`` a CourtListener API error surfaces as."""
        if exc.status_code == 401:
            # CL rejected a credential FastMCP accepted: drop it from
            # the token cache so the next request re-verifies.
            access_token = get_access_token()
            if access_token is not None:
                await get_session().invalidate_token(
                    access_token.token,
                    access_token.claims.get("token_kind", TokenKind.OAUTH),
                )
            message = (
                "CourtListener rejected the request as unauthorized. "
                "Your session may have expired; retry to re-authenticate."
            )
            if access_token is not None and access_token.claims.get("cached"):
                # A cached token expiring mid-session is routine.
                return SentryExemptToolError(message)
            # A freshly verified token CL rejects is a real disagreement.
            return UnauthorizedToolError(message, tool_name=self.name)
        if exc.status_code == 429:
            # The usage tool has its own throttle; don't point it at itself.
            hint = (
                ""
                if self.name == "get_api_usage"
                else "Call `get_api_usage` to see current usage and "
                "when the limit resets. "
            )
            return SentryExemptToolError(
                f"Rate limit exceeded: {exc}. {hint}For higher rate "
                "limits, you can upgrade your membership at "
                "https://donate.free.law/forms/membership"
            )
        if exc.status_code >= 500:
            return UpstreamCourtListenerError(
                f"CourtListener API error: {exc}",
                tool_name=self.name,
                status=str(exc.status_code),
            )
        return ToolError(
            f"CourtListener API error: {exc}", log_level=logging.WARNING
        )
