"""Healthcare Legal Tool for CourtListener MCP.

Pre-configured search tool for healthcare law practitioners covering:
- HIPAA / PHI compliance and breach litigation
- Healthcare whistleblower and retaliation cases
- Healthcare employment law
- Medical trade secret and IP cases

Contributed by Recipe Tech Solutions, Inc. (https://recipetechsolutions.ai)
"""

from mcp.types import CallToolResult, TextContent

from courtlistener.mcp_tools.mcp_tool import MCPTool

# Pre-built query templates for common healthcare legal scenarios
HEALTHCARE_QUERIES = {
    "hipaa_breach": {
        "description": "HIPAA PHI breach litigation and enforcement actions",
        "query": "HIPAA PHI breach protected health information",
        "type": "o",
    },
    "hipaa_whistleblower": {
        "description": "Healthcare whistleblower retaliation and protection cases",
        "query": "HIPAA whistleblower retaliation healthcare employer",
        "type": "o",
    },
    "phi_employer_retaliation": {
        "description": "Employee retaliation cases involving PHI concerns",
        "query": "PHI retaliation wrongful termination healthcare compliance",
        "type": "o",
    },
    "healthcare_trade_secret": {
        "description": "Trade secret cases in healthcare and medical technology",
        "query": "trade secret healthcare medical technology software",
        "type": "o",
    },
    "hipaa_civil_penalty": {
        "description": "HHS OCR civil money penalties and settlements",
        "query": "HHS OCR civil money penalty HIPAA settlement",
        "type": "o",
    },
    "prior_invention_assignment": {
        "description": "Prior invention assignment and IP ownership disputes",
        "query": "prior invention assignment employment agreement IP ownership",
        "type": "o",
    },
    "healthcare_employment": {
        "description": "Healthcare sector employment law and wrongful termination",
        "query": "healthcare employer wrongful termination employment retaliation",
        "type": "o",
    },
}


class HealthcareLegalTool(MCPTool):
    """Search for healthcare law cases including HIPAA, PHI, whistleblower, and employment cases.

    Provides pre-configured searches for common healthcare legal scenarios,
    making it easy to find relevant precedents without needing to construct
    complex queries from scratch.

    Available scenarios:
    - hipaa_breach: HIPAA PHI breach litigation
    - hipaa_whistleblower: Healthcare whistleblower retaliation
    - phi_employer_retaliation: PHI-related employee retaliation
    - healthcare_trade_secret: Medical technology trade secret cases
    - hipaa_civil_penalty: HHS OCR penalties and settlements
    - prior_invention_assignment: IP ownership and prior invention disputes
    - healthcare_employment: Healthcare employment law
    """

    name: str = "search_healthcare_legal"

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "scenario": {
                    "type": "string",
                    "description": (
                        "Pre-configured search scenario. One of: "
                        + ", ".join(HEALTHCARE_QUERIES.keys())
                    ),
                    "enum": list(HEALTHCARE_QUERIES.keys()),
                },
                "custom_query": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "description": (
                        "Optional custom query to use instead of the scenario template. "
                        "If provided, overrides the scenario query but keeps healthcare context."
                    ),
                    "default": None,
                },
                "max_results": {
                    "anyOf": [{"type": "integer"}, {"type": "null"}],
                    "description": "Maximum number of results to return (default: 10, max: 100).",
                    "default": 10,
                },
                "order_by": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "description": (
                        "Sort order for results. Options: 'score desc' (relevance), "
                        "'dateFiled desc' (newest first), 'dateFiled asc' (oldest first). "
                        "Default: 'score desc'."
                    ),
                    "default": "score desc",
                },
            },
            "required": ["scenario"],
        }

    def __call__(self, arguments: dict, session: dict) -> CallToolResult:
        """Execute a healthcare legal case search."""
        scenario = arguments.get("scenario")
        custom_query = arguments.get("custom_query")
        max_results = min(arguments.get("max_results") or 10, 100)
        order_by = arguments.get("order_by") or "score desc"

        if scenario not in HEALTHCARE_QUERIES:
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=f"Unknown scenario: {scenario}. Available: {', '.join(HEALTHCARE_QUERIES.keys())}",
                    )
                ]
            )

        template = HEALTHCARE_QUERIES[scenario]
        query = custom_query or template["query"]

        with self.get_client() as client:
            response = client.search.list(
                q=query,
                type=template["type"],
                order_by=order_by,
                page_size=max_results,
                stat_Precedential="on",
            )

            results = response.results
            count = response.current_page.count

            outputs = [
                f"HEALTHCARE LEGAL SEARCH: {template['description']}",
                f"Query: {query}",
                f"Total matching cases: {count}",
                f"Showing: {len(results)} results",
                "",
            ]

            for i, result in enumerate(results, 1):
                case_name = result.get(
                    "caseName", result.get("case_name", "Unknown Case")
                )
                date_filed = result.get(
                    "dateFiled", result.get("date_filed", "N/A")
                )
                court = result.get("court_id", result.get("court", "N/A"))
                citation = result.get("citation", "")
                absolute_url = result.get("absolute_url", "")
                snippet = result.get("snippet", "")

                outputs.append(f"[{i}] {case_name}")
                outputs.append(f"     Date: {date_filed} | Court: {court}")
                if citation:
                    outputs.append(f"     Citation: {citation}")
                if absolute_url:
                    outputs.append(
                        f"     URL: https://www.courtlistener.com{absolute_url}"
                    )
                if snippet:
                    outputs.append(f"     ...{snippet[:200]}...")
                outputs.append("")

            if not results:
                outputs.append(
                    "No results found. Try a custom_query for more specific searches."
                )

            return CallToolResult(
                content=[TextContent(type="text", text="\n".join(outputs))]
            )
