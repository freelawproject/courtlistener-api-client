---
name: release
description: Release a new version to PyPI by running the Release PR workflow, then follow its PR through merge and publish. Optional argument - patch, minor, major or an exact version (e.g. 2.1.0); defaults to patch.
argument-hint: "[patch|minor|major|X.Y.Z]"
---

# Release

Release a new version of `courtlistener-api-client` to PyPI. `$ARGUMENTS`
is the bump:

- (empty) or `patch`: e.g. `2.0.1` → `2.0.2`.
- `minor` or `major`: e.g. `2.0.1` → `2.1.0` or `3.0.0`.
- `X.Y.Z`: exactly that version. It must be higher than the current one.

## How releasing works

Two workflows do the work; this skill only starts the first and follows
along:

- **Release PR** (`.github/workflows/release_pr.yml`) runs every Monday
  and on demand. If `main` has commits since the last `v*` tag, it bumps
  the version in `pyproject.toml` and `uv.lock`, moves the "Upcoming"
  lists in `CHANGES.md` under the new version, and opens a PR from
  `release/next`. A scheduled run leaves an open release PR alone; a
  manual run rebuilds it from `main` with the bump you give it.
- **Release** (`.github/workflows/release.yml`) runs when that PR merges.
  It tags the merge commit `vX.Y.Z`, creates the GitHub release from the
  version's `CHANGES.md` section and starts the PyPI workflow on the tag.

## Steps

1. Start the Release PR workflow:
   ```sh
   gh workflow run release_pr.yml -f bump=<patch|minor|major>
   # or, for an exact version:
   gh workflow run release_pr.yml -f version=X.Y.Z
   ```
   Then find the run with `gh run list --workflow release_pr.yml` and
   `gh run watch` it. If it reports no commits since the last release,
   say so and stop.
2. Find the PR with `gh pr view release/next`. Check that its title has
   the version you expect and that the `CHANGES.md` section reads well.
3. CI doesn't run on PRs the workflow opens, so close and reopen the PR
   to start it: `gh pr close release/next && gh pr reopen release/next`.
4. Report the PR link. It needs an approving review; don't merge it
   yourself unless the user says to.
5. Once it merges, watch the Release run
   (`gh run list --workflow release.yml`), then the PyPI run it starts
   (`gh run list --workflow pypi.yml`). Report the result, and on success
   link `https://pypi.org/project/courtlistener-api-client/X.Y.Z/`. If a
   run fails, report the failure and stop. Don't delete or move the tag
   without the user's go-ahead, since PyPI never accepts the same version
   twice. If the Release run created the tag but no PyPI run started,
   start it with `gh workflow run pypi.yml --ref vX.Y.Z`; rerunning
   Release won't help, since it stops when the tag already exists.
