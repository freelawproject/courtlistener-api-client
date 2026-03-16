import json

from mcp.types import CallToolResult, TextContent

from courtlistener.mcp_tools.mcp_tool import MCPTool
from courtlistener.mcp_tools.utils import (
    collect_results,
    prepare_count_str,
    prepare_filter,
    prepare_query_id,
)
from courtlistener.models import ENDPOINTS

MAX_NUM_RESULTS = 100
DEFAULT_NUM_RESULTS = 20


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
            "num_results": {
                "type": "integer",
                "description": (
                    f"Number of results to return (default {DEFAULT_NUM_RESULTS}, "
                    f"max {MAX_NUM_RESULTS}). Use `get_more_results` to paginate."
                ),
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
            updated_properties[filter_name] = prepare_filter(
                filter,
                endpoint_id="search",
                field_name=filter_name,
            )
        return {
            "type": "object",
            "properties": updated_properties,
            "required": ["type"],
        }

    def __call__(self, arguments: dict, session: dict) -> CallToolResult:
        """Call the search tool."""
        client = self.get_shared_client(session)
        fields = arguments.pop("fields", None)
        num_results = min(
            max(arguments.pop("num_results", DEFAULT_NUM_RESULTS), 1),
            MAX_NUM_RESULTS,
        )
        response = client.search.list(**arguments)

        # Prepare the search session
        query_id = prepare_query_id(response, session)
        outputs = [f"Query ID: {query_id}"]

        # Prepare the count string
        count_str = prepare_count_str(
            response.current_page.count, query_id
        )
        outputs.append(count_str)

        # Collect results using autopagination
        results = collect_results(
            session["queries"][query_id], num_results
        )

        missing_fields = False
        filtered_results = results
        if fields:
            if any(k not in result for result in results for k in fields):
                missing_fields = True
            filtered_results = [
                {k: v for k, v in result.items() if k in fields}
                for result in results
            ]

        if missing_fields:
            outputs.append(
                f"WARNING: Some fields in {fields} not found in results.\n\n"
                f"Available fields: {', '.join(results[0].keys())}"
            )

        results_str = json.dumps(filtered_results, indent=2)
        outputs.append(results_str)

        if len(results) == num_results:
            outputs.append(
                f"Use `get_more_results` with query_id={query_id} "
                f"to retrieve additional results."
            )

        outputs_str = "\n\n".join([x for x in outputs if x]).strip()
        return CallToolResult(
            content=[TextContent(type="text", text=outputs_str)]
        )
