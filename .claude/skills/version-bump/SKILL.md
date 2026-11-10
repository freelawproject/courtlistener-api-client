---
name: version-bump
description: Bump the package version in a PR, then tag the merge commit so the PyPI workflow publishes the release. Optional argument - the version to release (e.g. 1.3.0); defaults to the next patch version.
argument-hint: [X.Y.Z]
---

# Version bump

Release a new version of `courtlistener-api-client` to PyPI. `$ARGUMENTS`
is the version:

- (empty): bump the patch number, e.g. `1.2.0` → `1.2.1`.
- `X.Y.Z`: release exactly that version, e.g. `1.3.0` or `2.0.0`. It
  must be higher than the current version.

## How releasing works

`.github/workflows/pypi.yml` builds and publishes to PyPI when a tag
matching `v*.*.*` is pushed. The PR only changes the version. The release
happens when the tag is pushed after the PR merges, so the tag has to
point at the merge commit on `main`, not at a commit on the PR branch.

## Steps

1. Pull the latest from main.
2. Read the current version from `version = "..."` in `pyproject.toml`
   and work out the new one from `$ARGUMENTS`. Check that
   `git tag --list "v$NEW_VERSION"` is empty.
3. Make a branch: `version-bump-$NEW_VERSION-$ISO_8601_DATE_WITHOUT_DASHES`
   (e.g. `version-bump-1.2.1-20261110`). Don't name it `v$NEW_VERSION`,
   since a branch with the same name as the tag makes the ref ambiguous.
4. Change the version in three places:
   - **`pyproject.toml`:** `version = "$NEW_VERSION"`.
   - **`uv.lock`:** run `uv lock` so the `courtlistener-api-client`
     package entry picks up the new version. Check that the diff touches
     only that entry. An old `uv` rewrites the whole lockfile in an older
     format; if that happens, discard the change and use a current `uv`.
   - **`CHANGES.md`:** under `## Upcoming` and its "not yet released"
     line, add a `### $NEW_VERSION - YYYY-MM-DD` heading (today's date)
     above the unreleased `Features:` / `Changes:` / `Fixes:` lists, so
     they become that release's notes. Above the new heading, add fresh,
     empty `Features:`, `Changes:` and `Fixes:` lists, each with a lone
     `-`, for the next release. Don't rewrite the existing entries.
5. Commit with `build(package): version bump to $NEW_VERSION`.
6. Push the branch and open the PR, titled
   `build(package): version bump to $NEW_VERSION`. The body lists the
   version change and summarizes the release notes, one line per section.
7. Wait for the PR to merge. It needs an approving review; don't merge it
   yourself unless the user says to.
8. Tag the merge commit and push the tag:
   ```sh
   git switch main && git pull
   git tag -a "v$NEW_VERSION" -m "Release version $NEW_VERSION"
   git push origin "v$NEW_VERSION"
   ```
   Before tagging, check that `HEAD` is the PR's merge commit
   (`gh pr view <n> --json mergeCommit`).
9. Watch the publish run with `gh run list --workflow pypi.yml` and
   `gh run watch`. Report the result, and on success link
   `https://pypi.org/project/courtlistener-api-client/$NEW_VERSION/`. If
   it fails, report the failure and stop. Don't delete or move the tag
   without the user's go-ahead, since PyPI never accepts the same version
   twice.

## Commit messages

Use Conventional Commits: `type(scope): description`. A version bump is
always `build(package): version bump to X.Y.Z`.
