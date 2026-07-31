from typing import Literal, get_args, get_origin

from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from courtlistener.mcp.exceptions import ToolArgumentValidationError
from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.utils import endpoint_id_property
from courtlistener.models import ENDPOINTS
from courtlistener.utils import did_you_mean


def related_example(
    field_name: str, field_info, related_class_name: str
) -> tuple[str, str]:
    """Return ``(related_endpoint_id, example)`` for a related filter."""
    related_id = related_class_name
    for endpoint in ENDPOINTS.values():
        if endpoint.__name__ == related_class_name:
            related_id = endpoint.endpoint_id
            break

    id_types = get_args(field_info.annotation)
    if related_id == "courts":
        example = f"{field_name}='scotus'"
    elif str in id_types:
        example = f"{field_name}='some-id'"
    else:
        example = f"{field_name}=12345"
    return related_id, example


class GetChoicesTool(MCPTool):
    """Get the valid choices for a field on a CourtListener API endpoint.

    Use this when a field's schema says to look up choices with this tool.
    """

    name: str = "get_choices"
    annotations = ToolAnnotations(
        title="Get Field Choices",
        readOnlyHint=True,
        destructiveHint=False,
        openWorldHint=False,
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "endpoint_id": endpoint_id_property(
                    "The endpoint the field belongs to.",
                    include_search=True,
                ),
                "field_name": {
                    "type": "string",
                    "description": "The field name to get choices for.",
                },
            },
            "required": ["endpoint_id", "field_name"],
            "additionalProperties": False,
        }

    async def __call__(
        self, arguments: dict, ctx: Context
    ) -> dict[str, list[dict] | str]:
        endpoint_id: str = arguments["endpoint_id"]
        field_name: str = arguments["field_name"]

        for endpoint in ENDPOINTS.values():
            if endpoint.endpoint_id != endpoint_id:
                continue

            field_info = endpoint.model_fields.get(field_name)
            if field_info is None:
                raise ToolArgumentValidationError(
                    f"Field '{field_name}' not found on endpoint "
                    f"'{endpoint_id}'."
                    f"{did_you_mean(field_name, list(endpoint.model_fields))}",
                    tool_name=self.name,
                    argument_names=["field_name"],
                )

            extra = getattr(field_info, "json_schema_extra", {}) or {}
            choices = extra.get("choices", [])
            if not choices and get_origin(field_info.annotation) is Literal:
                # If literal, provide the fixed values
                values = get_args(field_info.annotation)
                return {
                    "choices": [
                        {"value": v, "display_name": str(v)} for v in values
                    ],
                    "note": (
                        f"Field '{field_name}' is fixed to "
                        f"{', '.join(repr(v) for v in values)} on endpoint "
                        f"'{endpoint_id}'; there is nothing to choose."
                    ),
                }
            if not choices:
                if extra.get("related_class_name"):
                    # If a related field, explain to use id or related query
                    related_id, example = related_example(
                        field_name, field_info, extra["related_class_name"]
                    )
                    note = (
                        f"Field '{field_name}' on endpoint "
                        f"'{endpoint_id}' is a related-object filter, "
                        f"not a choice field: pass a {related_id} "
                        f"record's id (e.g. {example}) or a dict of "
                        f"{related_id} subfields."
                    )
                else:
                    # If a free-text field, explain
                    note = (
                        f"Field '{field_name}' on endpoint "
                        f"'{endpoint_id}' has no fixed choice list; it "
                        "accepts free-form values."
                    )
                # Provide a list of which fields do have choices
                choice_fields = sorted(
                    name
                    for name, f in endpoint.model_fields.items()
                    if (getattr(f, "json_schema_extra", None) or {}).get(
                        "choices"
                    )
                )
                if choice_fields:
                    note += (
                        f" Fields on '{endpoint_id}' that do have "
                        f"choices: {', '.join(choice_fields)}."
                    )
                return {"choices": [], "note": note}

            return {"choices": choices}

        # Unreachable: the schema's endpoint_id enum is validated in
        # ToolHandlerMiddleware before dispatch. Guards the fall-through.
        raise ValueError(f"Endpoint '{endpoint_id}' not found")
