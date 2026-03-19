import json

from mcp.types import CallToolResult, TextContent

from courtlistener.mcp.tools.mcp_tool import MCPTool
from courtlistener.mcp.tools.utils import (
    DEFAULT_NUM_RESULTS,
    MAX_NUM_RESULTS,
    collect_results,
    filter_fields,
    prepare_count_str,
    prepare_filter,
    prepare_has_more_str,
    prepare_query_id,
)
from courtlistener.models import ENDPOINTS


class SearchTool(MCPTool):
    """Search for case law, dockets, judges, and oral arguments.

    When returning results to the user, consider presenting them as
    color-coded visual cards with clickable "view on CourtListener" links
    rather than plain  text, grouping by relevance or significance where
    helpful. Fields like `absolute_url`, `caseName`, `dateFiled`, etc. can
    be useful here.
    """

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
                    f"Number of results to return (1-{MAX_NUM_RESULTS}). "
                    f"Defaults to {DEFAULT_NUM_RESULTS}."
                ),
                "minimum": 1,
                "maximum": MAX_NUM_RESULTS,
                "default": DEFAULT_NUM_RESULTS,
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
        with self.get_client(session) as client:
            fields = arguments.pop("fields", None)
            num_results = arguments.pop("num_results", DEFAULT_NUM_RESULTS)
            response = client.search.list(**arguments)

            # Collect results first so page_result_index is updated
            # before we dump state via prepare_query_id.
            results = collect_results(response, num_results)

            query_id = prepare_query_id(response, session, fields=fields)
            outputs = [f"Query ID: {query_id}"]

            count_str = prepare_count_str(
                response.current_page.count, query_id
            )
            outputs.append(count_str)

            filtered_results, missing_fields = filter_fields(results, fields)

            if missing_fields:
                outputs.append(
                    f"WARNING: Some fields in {fields} not found in results.\n\n"
                    f"Available fields: {', '.join(results[0].keys())}"
                )

            results_str = json.dumps(filtered_results, indent=2)
            outputs.append(results_str)

            has_more_str = prepare_has_more_str(response, query_id)
            outputs.append(has_more_str)

            outputs_str = "\n\n".join([x for x in outputs if x]).strip()
            return CallToolResult(
                content=[TextContent(type="text", text=outputs_str)]
            )
