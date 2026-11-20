"""Prepare a release: bump the version and roll CHANGES.md forward.

Used by the Release PR workflow, and runnable by hand:

    python scripts/release.py prepare [--bump patch|minor|major | --version X.Y.Z]
        Bumps the version in pyproject.toml (or sets an exact version,
        which must be higher than the current one), moves the "Upcoming" lists in
        CHANGES.md under a new "### X.Y.Z - YYYY-MM-DD" heading and adds
        fresh, empty lists for the next release. Prints the new version.
        Run `uv lock` afterwards so uv.lock picks up the version.

    python scripts/release.py version
        Prints the version in pyproject.toml.

    python scripts/release.py notes X.Y.Z
        Prints that release's section of CHANGES.md, for the GitHub
        release body.
"""

import argparse
import datetime
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
CHANGES = ROOT / "CHANGES.md"

VERSION_RE = re.compile(r'^version = "(\d+)\.(\d+)\.(\d+)"$', re.MULTILINE)
UNRELEASED_LINE = (
    "The following changes are not yet released, but are code complete:"
)
EMPTY_LISTS = "Features:\n-\n\nChanges:\n-\n\nFixes:\n-\n"


def current_version() -> tuple[int, int, int]:
    match = VERSION_RE.search(PYPROJECT.read_text())
    if not match:
        sys.exit("No version found in pyproject.toml")
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


def bump(version: tuple[int, int, int], part: str) -> str:
    major, minor, patch = version
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def roll_changes(text: str, new_version: str, today: str) -> str:
    """Move the Upcoming lists under a new release heading."""
    head, sep, rest = text.partition(UNRELEASED_LINE + "\n")
    if not sep:
        sys.exit(f"CHANGES.md is missing the line: {UNRELEASED_LINE}")
    return (
        f"{head}{sep}\n{EMPTY_LISTS}\n"
        f"### {new_version} - {today}\n\n{rest.lstrip()}"
    )


def parse_version(version: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        sys.exit(f"Not an X.Y.Z version: {version}")
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


def prepare(part: str, exact: str | None) -> None:
    current = current_version()
    if exact:
        if parse_version(exact) <= current:
            sys.exit(f"{exact} is not higher than the current version")
        new_version = exact
    else:
        new_version = bump(current, part)
    PYPROJECT.write_text(
        VERSION_RE.sub(f'version = "{new_version}"', PYPROJECT.read_text(), 1)
    )
    today = datetime.date.today().isoformat()
    CHANGES.write_text(roll_changes(CHANGES.read_text(), new_version, today))
    print(new_version)


def notes(version: str) -> None:
    """Print one release's section, without its heading."""
    text = CHANGES.read_text()
    match = re.search(
        rf"^### {re.escape(version)} - .*?\n(.*?)(?=^##)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        sys.exit(f"No CHANGES.md section for {version}")
    # Drop lists that are only a lone "-".
    body = re.sub(r"^\w+:\n-\n\n?", "", match.group(1), flags=re.MULTILINE)
    print(body.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("prepare")
    bump_group = prepare_parser.add_mutually_exclusive_group()
    bump_group.add_argument(
        "--bump", choices=["patch", "minor", "major"], default="patch"
    )
    bump_group.add_argument("--version", dest="exact")
    sub.add_parser("version")
    notes_parser = sub.add_parser("notes")
    notes_parser.add_argument("version")
    args = parser.parse_args()

    if args.command == "prepare":
        prepare(args.bump, args.exact)
    elif args.command == "version":
        print("{}.{}.{}".format(*current_version()))
    else:
        notes(args.version)


if __name__ == "__main__":
    main()
