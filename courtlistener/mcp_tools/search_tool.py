import json

from mcp.types import TextContent

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

        updated_properties = {}
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

    def __call__(self, arguments: dict, session: dict) -> list[TextContent]:
        """Call the search tool."""
        with self.get_client() as client:
            response = client.search.list(**arguments)
            return [
                TextContent(
                    type="text",
                    text=json.dumps(response.results, indent=2),
                )
            ]
