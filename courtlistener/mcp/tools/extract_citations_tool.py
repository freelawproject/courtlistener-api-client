"""MCP tool for local citation extraction using eyecite."""

from __future__ import annotations

from eyecite import get_citations, resolve_citations
from mcp.types import CallToolResult, TextContent

from courtlistener.mcp.tools.citation_utils import (
    citation_type_label,
    format_resolved_citations,
)
from courtlistener.mcp.tools.mcp_tool import MCPTool


class ExtractCitationsTool(MCPTool):
    """Extract and resolve legal citations from text using eyecite.

    Runs locally with no API calls or rate limits. Handles all
    citation types: full case citations, id., supra, short cites,
    and statutes.

    Use this tool to understand the citation structure of a document
    before selectively verifying citations with analyze_citations.
    """

    name: str = "extract_citations"

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Legal text to extract citations from.",
                },
                "resolve": {
                    "type": "boolean",
                    "description": (
                        "Whether to resolve id./supra/short cites to "
                        "their antecedents. Defaults to true."
                    ),
                    "default": True,
                },
            },
            "required": ["text"],
        }

    def __call__(self, arguments: dict, session: dict) -> CallToolResult:
        text = arguments["text"]
        resolve = arguments.get("resolve", True)

        cites = get_citations(text)

        if not cites:
            return CallToolResult(
                content=[TextContent(type="text", text="No citations found.")]
            )

        if not resolve:
            if not cites:
                output = "No citations found."
            else:
                lines = [f"Found {len(cites)} citation(s):\n"]
                for i, cite in enumerate(cites, 1):
                    label = citation_type_label(cite)
                    lines.append(f'  {i}. [{label}] "{cite.matched_text()}"')
                output = "\n".join(lines)
        else:
            resolutions = resolve_citations(cites)
            output = format_resolved_citations(cites, resolutions)

        return CallToolResult(content=[TextContent(type="text", text=output)])
