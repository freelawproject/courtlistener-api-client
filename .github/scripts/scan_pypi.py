#!/usr/bin/env python3
"""Scan PyPI for packages matching monitored terms and detect changes.

Fetches the PyPI Simple API index and JSON API for details on matches.
Stores results in a JSON file. Exits with code 1 if the package count
changes or on first run (to record the baseline).
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

# --- Configuration -----------------------------------------------------------

MONITOR_TERMS = [
    "courtlistener",
    "court-listener",
    "freelawproject",
    "free-law-project",
]

KNOWN_SAFE = {
    "courtlistener-api-client",
}

RESULTS_FILE = Path("results/pypi_packages.json")
PYPI_SIMPLE_URL = "https://pypi.org/simple/"
PYPI_JSON_URL = "https://pypi.org/pypi/{}/json"


# --- Helpers -----------------------------------------------------------------


def fetch_all_package_names() -> list[str]:
    """Fetch the full PyPI simple index as JSON."""
    req = urllib.request.Request(
        PYPI_SIMPLE_URL,
        headers={"Accept": "application/vnd.pypi.simple.v1+json"},
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    return [p["name"] for p in data["projects"]]


def fetch_package_details(package_name: str) -> dict:
    """Fetch detailed metadata for a single package."""
    url = PYPI_JSON_URL.format(package_name)
    try:
        with urllib.request.urlopen(url) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"name": package_name, "error": f"HTTP {e.code}"}

    info = data["info"]
    upload_time = None
    if data.get("urls"):
        upload_time = data["urls"][0].get("upload_time")

    return {
        "name": info["name"],
        "version": info.get("version"),
        "summary": info.get("summary"),
        "author": info.get("author"),
        "author_email": info.get("author_email"),
        "home_page": info.get("home_page"),
        "project_url": info.get("project_url"),
        "project_urls": info.get("project_urls"),
        "license": info.get("license"),
        "requires_python": info.get("requires_python"),
        "upload_time": upload_time,
        "is_known_safe": package_name in KNOWN_SAFE,
    }


def find_matching_packages(all_names: list[str]) -> list[str]:
    """Filter package names that contain any monitored term."""
    matches = set()
    for name in all_names:
        name_lower = name.lower()
        for term in MONITOR_TERMS:
            if term in name_lower:
                matches.add(name)
                break
    return sorted(matches)


def load_previous_results() -> dict | None:
    """Load previously stored scan results, if any."""
    if RESULTS_FILE.exists():
        return json.loads(RESULTS_FILE.read_text())
    return None


def compute_changes(previous: dict | None, current: dict) -> dict:
    """Compare previous and current package counts."""
    prev_count = len(previous["packages"]) if previous else None
    curr_count = len(current["packages"])

    prev_names = (
        {p["name"] for p in previous["packages"]} if previous else set()
    )
    curr_names = {p["name"] for p in current["packages"]}

    return {
        "is_first_run": previous is None,
        "prev_count": prev_count,
        "curr_count": curr_count,
        "count_changed": prev_count is not None and prev_count != curr_count,
        "new_packages": sorted(curr_names - prev_names) if previous else [],
        "removed_packages": sorted(prev_names - curr_names)
        if previous
        else [],
    }


# --- Main --------------------------------------------------------------------


def main():
    print("Starting PyPI namespace scan...")
    print(f"Monitoring terms: {MONITOR_TERMS}")
    print(f"Known safe packages: {KNOWN_SAFE}")
    print()

    # Step 1: Get all package names
    print("Fetching PyPI package index...")
    all_names = fetch_all_package_names()
    print(f"  Total packages on PyPI: {len(all_names):,}")

    # Step 2: Filter for matches
    matches = find_matching_packages(all_names)
    print(f"  Matching packages: {len(matches)}")
    for m in matches:
        safe_tag = " [KNOWN SAFE]" if m in KNOWN_SAFE else " [UNKNOWN]"
        print(f"    - {m}{safe_tag}")
    print()

    # Step 3: Get details for each match
    print("Fetching package details...")
    packages = []
    for name in matches:
        print(f"  Fetching {name}...")
        details = fetch_package_details(name)
        packages.append(details)

    # Step 4: Build current results
    current = {
        "scan_date": os.environ.get("SCAN_DATE", "unknown"),
        "monitor_terms": MONITOR_TERMS,
        "known_safe": sorted(KNOWN_SAFE),
        "total_pypi_packages": len(all_names),
        "packages": packages,
    }

    # Step 5: Compare with previous
    previous = load_previous_results()
    changes = compute_changes(previous, current)

    # Step 6: Save current results
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_FILE.write_text(json.dumps(current, indent=2) + "\n")
    print(f"\nResults saved to {RESULTS_FILE}")

    # Step 7: Report
    print("\n" + "=" * 60)
    print("SCAN REPORT")
    print("=" * 60)

    if changes["is_first_run"]:
        print("\nFirst run — recording baseline.")
        print(f"Package count: {changes['curr_count']}")
        for pkg in packages:
            safe = (
                " [KNOWN SAFE]" if pkg.get("is_known_safe") else " [UNKNOWN]"
            )
            print(f"  - {pkg['name']} v{pkg.get('version', '?')}{safe}")
            if pkg.get("summary"):
                print(f"    Summary: {pkg['summary']}")
            if pkg.get("author_email"):
                print(f"    Author: {pkg['author_email']}")
        print(
            "\nFailing to ensure baseline is stored. Next run will pass if count is stable."
        )
        return 1

    print(f"\nPrevious count: {changes['prev_count']}")
    print(f"Current count:  {changes['curr_count']}")

    if not changes["count_changed"]:
        print("\nPackage count unchanged. All clear!")
        return 0

    # Count changed — report details and fail
    print(
        f"\n🚨 PACKAGE COUNT CHANGED: {changes['prev_count']} → {changes['curr_count']}"
    )

    if changes["new_packages"]:
        print("\nNew packages:")
        for name in changes["new_packages"]:
            pkg = next((p for p in packages if p["name"] == name), {})
            safe = " [KNOWN SAFE]" if name in KNOWN_SAFE else " ⚠️  UNKNOWN"
            print(f"  - {name} v{pkg.get('version', '?')}{safe}")
            if pkg.get("summary"):
                print(f"    Summary: {pkg['summary']}")
            if pkg.get("author_email"):
                print(f"    Author: {pkg['author_email']}")
            if pkg.get("project_urls"):
                print(f"    URLs: {pkg['project_urls']}")

    if changes["removed_packages"]:
        print("\nRemoved packages:")
        for name in changes["removed_packages"]:
            print(f"  - {name}")

    print()
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write("has_changes=true\n")
            parts = []
            if changes["new_packages"]:
                parts.append(f"New: {', '.join(changes['new_packages'])}")
            if changes["removed_packages"]:
                parts.append(
                    f"Removed: {', '.join(changes['removed_packages'])}"
                )
            f.write(f"summary={'; '.join(parts)}\n")

    return 1


if __name__ == "__main__":
    sys.exit(main())
