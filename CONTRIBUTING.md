# Contributing to Bee With Me

Bee With Me tracks people in the field during rescue operations, and a regression can mean a
rescuer disappears from the map. That's why changes are reviewed and tested before they reach
`main`.

## Setup

Follow the [README](README.md#setup): PostGIS via `docker compose`, a Python 3.11+ virtualenv,
and Node.js 22.12+ (24 recommended, see `frontend/.nvmrc`).

## Workflow

1. **Branch from `main`.** Use `fix/<short-name>`, `feat/<short-name>`, or a release branch
   (`1.7.2`). Never push to `main` directly: the branch ruleset rejects it.
2. **Keep the tests green locally:**
   ```bash
   python -m pytest backend/tests/ --require-db     # needs the docker compose database running
   cd frontend && npm test && npm run build
   ```
3. **Open a pull request** and work through the template checklist.
4. **Required before merge:**
   - the **CI OK** check is green (it aggregates every job in `.github/workflows/ci.yml`);
   - one approving review from a code owner (`.github/CODEOWNERS`). Pushing new commits
     dismisses earlier approvals;
   - all review conversations resolved;
   - the branch is up to date with `main`.
5. **Squash-merge.** The PR title becomes the commit message, so write it like one
   (`fix(ui): …`, `feat(fire): …`). The branch is deleted automatically.

## Rules that are easy to miss

- **Database changes** go into a *new* numbered file in `backend/db/migrations/`. Released
  migration files are checksummed, so editing one breaks every existing install.
- **Bee protocol:** `docs/PROTOCOL.md` is the authoritative reference. Update it in the same PR
  as any parser change.
- **Scripts come in pairs.** `start.sh`/`start.ps1`, `scripts/backup.sh`/`backup.ps1`, and
  `restore.sh`/`restore.ps1` must behave the same. CI tests the PowerShell versions on Windows.
- **Bilingual UI.** Every new string needs both `en` and `bg` translations.
- **Changelog.** Add user-visible changes under `## [Unreleased]` in `CHANGELOG.md`.

## Releasing (maintainers)

1. Move the `[Unreleased]` notes under a new `## [X.Y.Z] - YYYY-MM-DD` heading.
2. Bump `APP_VERSION` in `backend/version.py` and `version` in `frontend/package.json`
   (run `npm install --package-lock-only` in `frontend/` to update the lockfile).
3. Merge that PR, then tag the merge commit on `main`:
   ```bash
   git tag -a vX.Y.Z -m "vX.Y.Z" && git push origin vX.Y.Z
   ```
4. `release.yml` checks the versions, reruns CI, and publishes the GitHub Release with the
   offline bundle and its SHA-256.

## Reporting security issues

Don't open a public issue. Use GitHub's **Report a vulnerability** button
(Security → Advisories) on this repository instead.
