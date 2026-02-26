import json

from mcp.types import CallToolResult, TextContent

from courtlistener.mcp_tools.mcp_tool import MCPTool
from courtlistener.mcp_tools.utils import prepare_filter
from courtlistener.models import ENDPOINTS


class SearchTool(MCPTool):
    """Search for case law, dockets, judges, and oral arguments."""

    name: str = "search"

    def get_input_schema(self) -> dict:
        """Get the input schema for the search tool."""
        search_endpoint = ENDPOINTS["search"]
        search_properties = search_endpoint.model_json_schema()["properties"]

        for endpoint_name, endpoint in ENDPOINTS.items():
            if endpoint_name.endswith("_search"):
                search_type_schema = endpoint.model_json_schema()
                search_type = search_type_schema["properties"]["type"]["const"]
                for filter_name in search_type_schema["properties"]:
                    if filter_name == "type":
                        continue
                    search_properties[filter_name]["search_types"] = (
                        search_properties[filter_name].get("search_types", [])
                        + [search_type]
                    )

        updated_properties = {
            "fields": {
                "anyOf": [
                    {"items": {"type": "string"}, "type": "array"},
                    {"type": "null"},
                ],
                "description": "Filter which fields are returned.",
            },
        }
        for filter_name, filter in list(search_properties.items()):
            # Add the valid types to the description
            if filter_name != "type":
                filter["description"] = (
                    filter.get("description", "")
                    + "\n\n"
                    + f"Valid when type in: {filter.get('search_types', [])}"
                ).strip()
            updated_properties[filter_name] = prepare_filter(filter)
        return {
            "type": "object",
            "properties": updated_properties,
            "required": ["type"],
        }

    def __call__(
        self, arguments: dict, session: dict
    ) -> list[TextContent] | CallToolResult:
        """Call the search tool."""
        with self.get_client() as client:
            fields = arguments.pop("fields", None)
            response = client.search.list(**arguments)
            results = response.results

            missing_fields = False
            filtered_results = results
            if fields:
                if any(k not in result for result in results for k in fields):
                    missing_fields = True
                filtered_results = [
                    {k: v for k, v in result.items() if k in fields}
                    for result in results
                ]

            text = json.dumps(filtered_results, indent=2)
            if missing_fields:
                text = (
                    f"WARNING: Some fields in {fields} not found in results.\n\n"
                    f"Available fields: {', '.join(results[0].keys())}\n\n"
                ) + text

            return [TextContent(type="text", text=text)]
