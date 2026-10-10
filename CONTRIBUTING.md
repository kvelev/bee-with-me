# Contributing to Bee With Me

Bee With Me tracks people in the field during rescue operations, and a regression can mean a
rescuer disappears from the map. That's why changes are reviewed and tested before they reach
`main`.

## Setup

Follow the [README](README.md#setup): PostGIS via `docker compose`, a Python 3.11+ virtualenv,
and Node.js 22.12+ (24 recommended, see `frontend/.nvmrc`).

## Branching model

```
feature/<name> ──PR──▶ develop ──(auto-deploy)──▶ develop environment
                          │
                 release/X.Y.Z ──PR──▶ main          (not deployed anywhere)
```

- **`develop`** is the integration branch. Every merge into it is tested, built into images and
  deployed to the develop environment by `.github/workflows/deploy-develop.yml`.
- **`main`** only receives finished releases. Nothing is pushed to `main` or `develop`
  directly: both branch rulesets require a pull request and a green **CI OK**.
- **`deploy/develop`** is written by CI only (develop + one commit pinning the image tags) and
  is what the develop environment syncs. Never branch from it or push to it.

## Workflow

1. **Branch from `develop`.** Use `feature/<short-name>` (or `fix/<short-name>`).
2. **Keep the tests green locally.** Enable the pre-commit hook once per clone; it runs the
   fast suites for whatever part of the repo you commit (frontend ~10 s, backend without the
   database ~1 min, script tests only when scripts change):
   ```bash
   git config core.hooksPath .githooks
   ```
   Before opening the PR, run the full suites (CI runs them anyway and must pass to merge):
   ```bash
   python -m pytest backend/tests/ --require-db     # needs the docker compose database running
   cd frontend && npm test && npm run build
   ```
3. **Open a pull request into `develop`** and work through the template checklist.
4. **Required before merge:**
   - the **CI OK** check is green (it aggregates every job in `.github/workflows/ci.yml`);
   - all review conversations resolved;
   - the branch is up to date with `develop`.
5. **Squash-merge.** The PR title becomes the commit message, so write it like one
   (`fix(ui): …`, `feat(fire): …`). The branch is deleted automatically.
6. **Check it on the develop environment** once the *Deploy develop* run finishes; it picks
   the new images up within a few minutes.

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

1. Cut `release/X.Y.Z` from `develop`. On that branch, move the `[Unreleased]` notes under a new `## [X.Y.Z] - YYYY-MM-DD` heading.
2. Bump `APP_VERSION` in `backend/version.py` and `version` in `frontend/package.json`
   (run `npm install --package-lock-only` in `frontend/` to update the lockfile).
3. Open a PR `release/X.Y.Z` → `main`. It needs a code-owner approval, and it is merged with
   a **merge commit**, not a squash, so `main` and `develop` keep sharing history. Then tag
   the merge commit on `main`:
   ```bash
   git tag -a vX.Y.Z -m "vX.Y.Z" && git push origin vX.Y.Z
   ```
4. `release.yml` checks the versions, reruns CI, and publishes the GitHub Release with the
   offline bundle and its SHA-256.

## Reporting security issues

Don't open a public issue. Use GitHub's **Report a vulnerability** button
(Security → Advisories) on this repository instead.
