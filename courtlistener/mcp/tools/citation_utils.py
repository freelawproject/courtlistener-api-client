"""Shared utilities for citation MCP tools."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

from courtlistener.citation_lookup import parse_wait_until

from eyecite.models import (
    CitationBase,
    FullCaseCitation,
    FullCitation,
    FullLawCitation,
    IdCitation,
    ShortCaseCitation,
    SupraCitation,
    UnknownCitation,
)
from eyecite.models import (
    Resource as CitationResource,
)
from eyecite.utils import DISALLOWED_NAMES

# Delimiter used between citations in the compact string sent to the
# citation-lookup API.  Semicolon-space is a natural Bluebook list
# separator that eyecite reliably parses without cleanup.
CITATION_DELIMITER = "; "

# Maximum citations per API request before 429 throttling.
MAX_CITATIONS_PER_REQUEST = 250

# Similarity below this is flagged as a possible hallucinated citation
# (volume+reporter+page match, but the case name does not).
CASE_NAME_MATCH_THRESHOLD = 0.8

_VS_PATTERN = re.compile(r"\b(vs?\.?|versus)\b", re.IGNORECASE)
_NON_WORD_PATTERN = re.compile(r"[^\w\s]")
_WHITESPACE_PATTERN = re.compile(r"\s+")

# Generic party-name phrases drawn from eyecite's DISALLOWED_NAMES list.
# Only the lowercase-in-source entries are party terms worth stripping
# ("state", "united states", etc.); the capitalized AG-surname entries in
# that list exist for eyecite's own extraction filter, not for
# name-weight adjustment. Sorted longest-first so multi-word phrases
# (e.g. "united states") match before their single-word overlaps.
_STOP_PHRASES: tuple[tuple[str, ...], ...] = tuple(
    sorted(
        (tuple(p.split()) for p in DISALLOWED_NAMES if p == p.lower()),
        key=len,
        reverse=True,
    )
)


def normalize_case_name(name: str | None) -> str:
    """Normalize a case name for comparison.

    Lowercases, collapses ``v.``/``vs.``/``versus`` to ``v``, strips
    punctuation, and collapses whitespace. Returns empty string for
    None/empty input.
    """
    if not name:
        return ""
    s = name.lower()
    s = _VS_PATTERN.sub("v", s)
    s = _NON_WORD_PATTERN.sub(" ", s)
    s = _WHITESPACE_PATTERN.sub(" ", s).strip()
    return s


def _strip_generic_party_terms(normalized: str) -> str:
    """Drop tokens matching generic party phrases (e.g. "united states").

    Operates on an already-normalized string (lowercase, punctuation
    stripped). Multi-word phrases are matched greedily against contiguous
    token runs.
    """
    tokens = normalized.split()
    out: list[str] = []
    i = 0
    while i < len(tokens):
        for phrase in _STOP_PHRASES:
            n = len(phrase)
            if tuple(tokens[i : i + n]) == phrase:
                i += n
                break
        else:
            out.append(tokens[i])
            i += 1
    return " ".join(out)


def case_name_similarity(a: str | None, b: str | None) -> float:
    """Return a 0.0-1.0 similarity score between two case names.

    Generic party phrases from eyecite's DISALLOWED_NAMES (e.g.
    ``"united states"``, ``"state"``, ``"people"``) are stripped before
    token comparison so the signal comes from the discriminating parts
    of the name, not shared prosecutorial prefixes. Combines token-set
    Jaccard with a subset boost (short form contained in long form
    scores 1.0) and falls back to character-level ``difflib`` ratio for
    non-tokenizable edge cases. Returns 0.0 if either side normalizes
    to empty.
    """
    na, nb = normalize_case_name(a), normalize_case_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    # Prefer comparing the discriminating tokens. Fall back to the
    # unstripped forms when stripping empties one side (e.g. a name made
    # entirely of generic terms).
    sa, sb = _strip_generic_party_terms(na), _strip_generic_party_terms(nb)
    if not sa or not sb:
        sa, sb = na, nb
    ta, tb = set(sa.split()), set(sb.split())
    if ta and tb:
        smaller, larger = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
        if smaller.issubset(larger):
            return 1.0
        jaccard = len(ta & tb) / len(ta | tb)
    else:
        jaccard = 0.0
    return max(jaccard, SequenceMatcher(None, sa, sb).ratio())


def input_case_name(cite: FullCaseCitation) -> str | None:
    """Extract the input case name from an eyecite FullCaseCitation.

    Returns ``"Plaintiff v. Defendant"`` when both are present, otherwise
    whichever single party name is available, or None.
    """
    meta = cite.metadata
    plaintiff = getattr(meta, "plaintiff", None)
    defendant = getattr(meta, "defendant", None)
    if plaintiff and defendant:
        return f"{plaintiff} v. {defendant}"
    return plaintiff or defendant or None


def case_name_mismatch(result: dict, input_case_name: str | None) -> bool:
    """True if a FOUND result's cluster name diverges from the input name.

    Only reports mismatches for status=200 with both an input case name
    and a verified cluster name available.
    """
    if not input_case_name or result.get("status") != 200:
        return False
    clusters = result.get("clusters", [])
    if not clusters:
        return False
    verified_name = clusters[0].get("case_name")
    if not verified_name:
        return False
    similarity = case_name_similarity(input_case_name, verified_name)
    return similarity < CASE_NAME_MATCH_THRESHOLD


def citation_type_label(cite: CitationBase) -> str:
    """Human-readable label for a citation type."""
    labels = {
        FullCaseCitation: "full",
        ShortCaseCitation: "short",
        IdCitation: "id.",
        SupraCitation: "supra",
        FullLawCitation: "statute",
        UnknownCitation: "unknown",
    }
    return labels.get(type(cite), type(cite).__name__)


def canonical_key(cite: FullCitation) -> str:
    """Canonical key for deduplication: 'volume reporter page'."""
    g = cite.groups
    return f"{g['volume']} {g['reporter']} {g['page']}"


def format_rate_limit_note(detail: Any, *, resumable_with: str) -> str:
    """Build a one-line note describing the upstream rate limit.

    Always returns a usable message — when ``wait_until`` can't be
    parsed, falls back to advice without a timestamp. ``resumable_with``
    names the tool to call next (e.g. ``resume_citation_analysis``).
    """
    target = parse_wait_until(detail)
    base = (
        f"Rate limited by the upstream API. Call `{resumable_with}` to "
        f"retry; set `wait=true` to have the server sleep through the "
        f"rate-limit window."
    )
    if target is None:
        return base
    seconds = max(0, int((target - datetime.now(timezone.utc)).total_seconds()))
    return (
        f"Rate limited by the upstream API (retry in ~{seconds}s, "
        f"wait_until={target.isoformat()}). Call `{resumable_with}` "
        f"with `wait=true` to have the server sleep through the window."
    )


def format_unresolved_section(unresolved: list[CitationBase]) -> list[str]:
    """Render the Unresolved section, deduped by (label, matched text).

    Eyecite emits every textual occurrence of short forms (``id.``,
    ``supra``, repeated short cites), so the raw list is noisy. Collapse
    identical rows into one with a reference count, matching how the
    resolved-cases section presents repeats.
    """
    counts: dict[tuple[str, str], int] = {}
    order: list[tuple[str, str]] = []
    for c in unresolved:
        key = (citation_type_label(c), c.matched_text() or "")
        if key not in counts:
            order.append(key)
        counts[key] = counts.get(key, 0) + 1

    lines = ["\nUnresolved:"]
    for i, key in enumerate(order, 1):
        label, text = key
        n = counts[key]
        suffix = f" — {n} reference(s)" if n > 1 else ""
        lines.append(f'  {i}. [{label}] "{text}"{suffix}')
    return lines


def format_resolved_citations(
    cites: list[CitationBase],
    resolutions: Any,
) -> str:
    """Format citations grouped by resolved resource."""
    cases: list[tuple[CitationResource, list[CitationBase]]] = []
    statutes: list[tuple[CitationResource, list[CitationBase]]] = []

    for resource, cite_list in resolutions.items():
        primary = resource.citation
        if isinstance(primary, FullCaseCitation):
            cases.append((resource, cite_list))
        elif isinstance(primary, FullLawCitation):
            statutes.append((resource, cite_list))

    # Find unresolved citations (not in any resource)
    resolved_ids = set()
    for cite_list in resolutions.values():
        for c in cite_list:
            resolved_ids.add(id(c))
    unresolved = [c for c in cites if id(c) not in resolved_ids]

    total = len(cites)
    parts = []
    summary_parts = []
    if cases:
        summary_parts.append(f"{len(cases)} unique case(s)")
    if statutes:
        summary_parts.append(f"{len(statutes)} statute(s)")
    if unresolved:
        summary_parts.append(f"{len(unresolved)} unresolved")

    parts.append(
        f"Found {total} citation(s) referencing "
        + ", ".join(summary_parts)
        + ".\n"
    )

    if cases:
        parts.append("Cases:")
        for i, (resource, cite_list) in enumerate(cases, 1):
            primary = resource.citation
            key = canonical_key(primary)
            meta = primary.metadata
            name = ""
            if meta.plaintiff and meta.defendant:
                name = f"{meta.plaintiff} v. {meta.defendant}"
            year = meta.year or ""
            header = f"  {i}. {key}"
            if name:
                header += f" ({name}"
                if year:
                    header += f", {year}"
                header += ")"
            elif year:
                header += f" ({year})"
            header += f" — {len(cite_list)} reference(s)"
            parts.append(header)
            for c in cite_list:
                label = citation_type_label(c)
                parts.append(f'       [{label}] "{c.matched_text()}"')

    if statutes:
        parts.append("\nStatutes:")
        for i, (resource, cite_list) in enumerate(statutes, 1):
            primary = resource.citation
            parts.append(
                f'  {i}. "{primary.matched_text()}" '
                f"— {len(cite_list)} reference(s)"
            )
            for c in cite_list:
                if c is not primary:
                    label = citation_type_label(c)
                    parts.append(f'       [{label}] "{c.matched_text()}"')

    if unresolved:
        parts.extend(format_unresolved_section(unresolved))

    return "\n".join(parts)


def build_compact_string(unique_citations: list[str]) -> str:
    """Join unique citation strings with our delimiter for the API."""
    return CITATION_DELIMITER.join(unique_citations)


def process_api_results(
    results: list[dict],
    batch: list[str],
    verified: dict[str, dict],
    pending: list[str],
) -> None:
    """Process API results, updating verified and pending dicts.

    Each API result is matched back to the batch citation it belongs
    to by comparing the citation text. Results with status 429 are
    left in pending for later retry.

    After processing all results, any batch citations that received
    no API result at all are marked as unresolvable and removed from
    pending. Without this sweep, citations the API doesn't recognize
    (e.g. slip opinion cites like "586 U. S. None") would stay in
    pending forever, causing resume_citation_analysis to loop
    infinitely.
    """
    rate_limited_keys: set[str] = set()

    for result in results:
        citation_text = result.get("citation", "")
        status = result.get("status")

        # Match this result to a batch citation
        matched_key = None
        if citation_text in batch:
            matched_key = citation_text
        else:
            normalized = citation_text.strip().lower()
            for key in batch:
                if key.strip().lower() == normalized:
                    matched_key = key
                    break

        if matched_key is None:
            continue

        if status == 429:
            # Rate-limited — leave in pending for retry
            rate_limited_keys.add(matched_key)
            continue

        # Summarize clusters to reduce stored data
        clusters = [
            {
                "cluster_id": cluster.get("id"),
                "case_name": cluster.get("case_name"),
                "case_name_short": cluster.get("case_name_short"),
                "date_filed": cluster.get("date_filed"),
                "citation_count": cluster.get("citation_count"),
                "precedential_status": cluster.get("precedential_status"),
                "absolute_url": cluster.get("absolute_url"),
                "docket_id": cluster.get("docket"),
                "citations": [
                    f"{c['volume']} {c['reporter']} {c['page']}"
                    for c in cluster.get("citations", [])
                    if c.get("volume") and c.get("reporter") and c.get("page")
                ],
            }
            for cluster in result.get("clusters", [])
        ]

        verified[matched_key] = {
            "status": status,
            "citation": citation_text,
            "clusters": clusters,
            "error_message": result.get("error_message"),
        }
        if matched_key in pending:
            pending.remove(matched_key)

    # Sweep: mark batch citations that got no API result as unresolvable.
    # Only skip citations that were explicitly rate-limited (429), since
    # those should genuinely be retried.
    for key in batch:
        if key in verified or key in rate_limited_keys:
            continue
        verified[key] = {
            "status": None,
            "citation": key,
            "clusters": [],
            "error_message": "No result returned by API",
        }
        if key in pending:
            pending.remove(key)


def _auto_resolve_identical_clusters(
    clusters: list[dict],
) -> dict | None:
    """If all candidate clusters have the same normalized name, pick one.

    Selection: highest ``citation_count`` (tie-break: earliest
    ``date_filed``). Returns the chosen cluster, or None if names differ.
    """
    if len(clusters) < 2:
        return None
    names = {normalize_case_name(c.get("case_name")) for c in clusters}
    names.discard("")
    if len(names) != 1:
        return None

    def sort_key(c: dict) -> tuple[int, str]:
        # Negative citation_count so higher counts sort first; ascending
        # date_filed so the earliest wins on ties.
        return (-(c.get("citation_count") or 0), c.get("date_filed") or "")

    return sorted(clusters, key=sort_key)[0]


def _format_found_cluster(
    citation_key: str,
    cluster: dict,
    ref_count: int,
    ref_breakdown: str,
    index: int,
    input_case_name: str | None,
) -> str:
    """Render a FOUND cluster, warning when the input case name diverges."""
    name = cluster.get("case_name", "Unknown")
    date = cluster.get("date_filed", "")
    cite_count = cluster.get("citation_count", 0)
    url = cluster.get("absolute_url", "")
    parallel = cluster.get("citations", [])
    cluster_id = cluster.get("cluster_id")

    similarity: float | None = None
    mismatch = False
    if input_case_name:
        similarity = case_name_similarity(input_case_name, name)
        mismatch = similarity < CASE_NAME_MATCH_THRESHOLD

    header = f"  {index}. {citation_key} — {name}"
    if date:
        header += f" ({date})"
    lines = [header]
    if mismatch:
        lines.append(
            "     WARNING: Input case name "
            f'"{input_case_name}" differs from verified "{name}" '
            f"(similarity {similarity:.2f}). Possible hallucinated citation."
        )
    lines.append(f"     Status: FOUND (cited by {cite_count} opinion(s))")
    if cluster_id is not None:
        lines.append(f"     Cluster ID: {cluster_id}")
    lines.append(f"     References in document: {ref_count} ({ref_breakdown})")
    if url:
        lines.append(f"     URL: https://www.courtlistener.com{url}")
    if parallel:
        lines.append(f"     Parallel citations: {', '.join(parallel)}")
    return "\n".join(lines)


def format_verification_result(
    citation_key: str,
    result: dict,
    ref_count: int,
    ref_breakdown: str,
    index: int,
    input_case_name: str | None = None,
) -> str:
    """Format a single verified citation for display.

    When ``input_case_name`` is provided and a FOUND result's cluster
    case name differs significantly (similarity below
    ``CASE_NAME_MATCH_THRESHOLD``), a warning is prepended to flag
    possible hallucinated citations. An AMBIGUOUS result whose candidate
    clusters all share the same normalized name is auto-resolved to the
    most-cited cluster, tie-breaking on earliest ``date_filed``.
    """
    status = result.get("status")
    if status == 200:
        clusters = result.get("clusters", [])
        if not clusters:
            return (
                f"  {index}. {citation_key}\n"
                f"     Status: FOUND (no cluster details)\n"
                f"     References in document: {ref_count} ({ref_breakdown})"
            )
        cluster = clusters[0]
        return _format_found_cluster(
            citation_key,
            cluster,
            ref_count,
            ref_breakdown,
            index,
            input_case_name,
        )

    elif status == 404:
        return (
            f"  {index}. {citation_key}\n"
            f"     Status: NOT FOUND — may be incorrect or not in CourtListener\n"
            f"     References in document: {ref_count} ({ref_breakdown})"
        )
    elif status == 300:
        clusters = result.get("clusters", [])
        resolved = _auto_resolve_identical_clusters(clusters)
        if resolved is not None:
            other_ids = [
                c.get("cluster_id")
                for c in clusters
                if c is not resolved and c.get("cluster_id") is not None
            ]
            note = (
                f"     Auto-resolved from {len(clusters)} clusters with "
                f"identical name; other cluster IDs: "
                f"{', '.join(str(i) for i in other_ids)}"
            )
            body = _format_found_cluster(
                citation_key,
                resolved,
                ref_count,
                ref_breakdown,
                index,
                input_case_name,
            )
            return body + "\n" + note

        candidate_lines = []
        for c in clusters:
            name = c.get("case_name", "?")
            cid = c.get("cluster_id")
            date = c.get("date_filed") or ""
            count = c.get("citation_count")
            extras = []
            if cid is not None:
                extras.append(f"cluster_id={cid}")
            if date:
                extras.append(date)
            if count is not None:
                extras.append(f"cited by {count}")
            suffix = f" ({'; '.join(extras)})" if extras else ""
            candidate_lines.append(f"       - {name}{suffix}")
        return (
            f"  {index}. {citation_key}\n"
            f"     Status: AMBIGUOUS — matches {len(clusters)} cases:\n"
            + "\n".join(candidate_lines)
            + f"\n     References in document: {ref_count} ({ref_breakdown})"
        )
    elif status == 400:
        return (
            f"  {index}. {citation_key}\n"
            f"     Status: INVALID — could not be parsed by the API\n"
            f"     References in document: {ref_count} ({ref_breakdown})"
        )
    elif status is None:
        error = result.get("error_message", "")
        reason = error if error else "citation not recognized by API"
        return (
            f"  {index}. {citation_key}\n"
            f"     Status: UNRESOLVABLE — {reason}\n"
            f"     References in document: {ref_count} ({ref_breakdown})"
        )
    else:
        return (
            f"  {index}. {citation_key}\n"
            f"     Status: {status}\n"
            f"     References in document: {ref_count} ({ref_breakdown})"
        )


def format_analysis(
    analysis_id: str,
    cites: list[CitationBase],
    resolutions: Any,
    resource_refs: dict[str, dict],
    unique_citations: list[str],
    verified: dict[str, dict],
    pending: list[str],
    input_case_names: dict[str, str] | None = None,
) -> str:
    """Format the full analysis output.

    Terminology used below:

    * **citation occurrence** — one citation as it appears in the text.
    * **unique citation string** — distinct ``volume reporter page``
      triples; many occurrences can share one string (e.g., a case cited
      three times).
    * **unique case cluster** — distinct CourtListener case clusters
      after parallel-citation dedup; several strings can map to one
      cluster.
    """
    input_case_names = input_case_names or {}
    # Count by type
    case_count = sum(
        1 for r in resolutions if isinstance(r.citation, FullCaseCitation)
    )
    statute_count = sum(
        1 for r in resolutions if not isinstance(r.citation, FullCaseCitation)
    )
    # Find unresolved
    resolved_ids = set()
    for cite_list in resolutions.values():
        for c in cite_list:
            resolved_ids.add(id(c))
    unresolved = [c for c in cites if id(c) not in resolved_ids]

    parts = [f"Citation Analysis (Job ID: {analysis_id})\n"]

    # Summary line
    extraction_parts = [f"{len(cites)} citation occurrence(s)"]
    extraction_parts.append(
        f"{len(unique_citations)} unique citation string(s)"
    )
    if case_count:
        extraction_parts.append(f"{case_count} unique case cluster(s)")
    if statute_count:
        extraction_parts.append(f"{statute_count} statute(s)")
    if unresolved:
        extraction_parts.append(f"{len(unresolved)} unresolved")
    parts.append("Extraction: " + ", ".join(extraction_parts) + ".")

    verified_count = len(verified)
    total_unique = len(unique_citations)
    pending_count = len(pending)
    verification_line = (
        f"Verification: {verified_count} of {total_unique} verified."
    )
    if pending_count:
        verification_line += (
            f" ({pending_count} pending — use resume_citation_analysis "
            f'with job_id="{analysis_id}")'
        )
    parts.append(verification_line)

    mismatch_count = sum(
        1
        for key in verified
        if case_name_mismatch(verified[key], input_case_names.get(key))
    )
    if mismatch_count:
        parts.append(
            f"WARNING: {mismatch_count} citation(s) matched by reporter "
            "but case name differs significantly — possible hallucinations."
        )

    # Verified cases
    if verified or pending:
        parts.append("\nCases:")
        idx = 1
        for key in unique_citations:
            refs = resource_refs.get(key, {})
            ref_count = refs.get("ref_count", 1)
            ref_breakdown = refs.get("ref_breakdown", "")

            if key in verified:
                parts.append(
                    format_verification_result(
                        key,
                        verified[key],
                        ref_count,
                        ref_breakdown,
                        idx,
                        input_case_names.get(key),
                    )
                )
            else:
                parts.append(f"  {idx}. {key}\n     Status: PENDING")
            idx += 1

    # Statutes
    statute_resources = [
        (r, cl)
        for r, cl in resolutions.items()
        if not isinstance(r.citation, FullCaseCitation)
    ]
    if statute_resources:
        parts.append("\nStatutes:")
        for i, (resource, cite_list) in enumerate(statute_resources, 1):
            primary = resource.citation
            count = len(cite_list)
            parts.append(
                f'  {i}. "{primary.matched_text()}" — {count} reference(s)'
            )

    # Unresolved
    if unresolved:
        parts.extend(format_unresolved_section(unresolved))

    return "\n".join(parts)


def format_resume(
    job_id: str,
    job: dict,
    newly_verified: set[str],
) -> str:
    """Format the resume output showing newly verified citations."""
    verified = job["verified"]
    pending = job["pending"]
    unique = job["unique_citations"]
    resource_refs = job["resource_refs"]
    input_case_names = job.get("input_case_names", {})
    total = len(unique)

    parts = [f"Citation Analysis (Job ID: {job_id}) — Resumed\n"]

    parts.append(f"Verification: {len(verified)} of {total} verified.")
    if pending:
        parts.append(
            f"({len(pending)} still pending — call "
            f'resume_citation_analysis again with job_id="{job_id}")'
        )
    else:
        parts.append("All citations verified!")

    if newly_verified:
        parts.append(f"\nNewly verified ({len(newly_verified)}):")
        idx = 1
        for key in unique:
            if key in newly_verified:
                refs = resource_refs.get(key, {})
                ref_count = refs.get("ref_count", 1)
                ref_breakdown = refs.get("ref_breakdown", "")
                parts.append(
                    format_verification_result(
                        key,
                        verified[key],
                        ref_count,
                        ref_breakdown,
                        idx,
                        input_case_names.get(key),
                    )
                )
                idx += 1
    elif pending:
        parts.append(
            "\nNo new citations verified in this batch "
            "(may still be rate-limited)."
        )

    return "\n".join(parts)
