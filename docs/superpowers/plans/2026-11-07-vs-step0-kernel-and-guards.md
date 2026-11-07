# Vertical slices, step 0: kernel package and architecture guards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the shared kernel files into `backend/core/` behind thin re-exports, pin the architecture-test tooling with a ratchet allowlist of today's violations, and add the module-manifest contract and the request-ID middleware, with no change an operator can notice.

**Architecture:** Five small, individually revertable moves (`config`, `database`, `json_columns`, `ws`, token functions of `auth`) each leave the old import path alive as a shim that *is* the new module (`sys.modules` alias), so patches, shared state and `from backend import ws` keep working. Guards come after the moves: `import-linter` for import rules (allowlist inside its config, stale entries fail), plain pytest for SQL ownership and manifest completeness (allowlist in JSON), `dependency-cruiser` driven from vitest on the frontend. All allowlists are exact-match ratchets.

**Tech Stack:** Python 3.11+, FastAPI, pydantic-settings, `import-linter` (new), pytest; Vue 3 + vitest, `dependency-cruiser` (new).

**Spec:** `docs/superpowers/specs/2026-10-31-vertical-slices-programme-design.md` (workspace kit, not in this repo; sections 5 "Step 0", 6, 7), `Architecture/application/modular-monolith.md` sections 3, 4, 9, ADR 17 (Accepted), ADR 18 and ADR 19 (Proposed). `docs/PROTOCOL.md` is not touched.

**Base:** `upstream/develop` at `cdc8f51` (PR #70). Branch for this plan: `docs/vs-step0-plan`. Execution branches: `feature/vs-0-<task>` off `develop`, one PR each.

## Global Constraints

- Kernel package is `backend/core/` (never `platform/`: it shadows the stdlib `platform` module when `backend/` is on `sys.path`). Frontend keeps `src/platform/`.
- Moved: `database.py`, `json_columns.py`, `config.py`, `auth.py` (token functions only), `ws.py`. Not moved and not re-exports: `backend/main.py`, `backend/db/migrate.py`, `backend/version.py`.
- Old import paths stay thin re-exports until step 5. Production importers are **not** repointed in step 0 (smaller diffs, no conflicts with in-flight branches); they are recorded in the allowlist and shrink with their module's step.
- `ws.py` moves as it is: no authentication hook, no origin check, no behaviour change. Nothing from Phase 3 is implemented. `hardware_reader/*` is not edited.
- No migrations, no schema change, no `data/`, `tiles/`, `backend/uploads/`, `.env` access. Owner-written files (`README.md`, `CHANGELOG.md`, `todo.md`, `.github/workflows/**`, `docker/docker-compose.yaml`) are not edited: proposals go to the owner (section "Open to the owner").
- Every test under `backend/tests/modules/**` and every frontend test stays green and unedited except import paths. The one known path edit: `backend/tests/test_smoke_script.py:444` reads the text of `backend/ws.py`.
- New dependencies carry a version: `import-linter>=2.16,<3` in `backend/requirements.txt`, `dependency-cruiser` as an exact version in `frontend/package.json` devDependencies (resolve with `npm view dependency-cruiser version` when executing, record the number in the commit message).
- Tags: pytest `@pytest.mark.Trait("Task", "T3xx")`, vitest `it('... [T3xx]', ...)`. Commits: `type(scope): T3xx summary`, body ends with the Co-Authored-By line from the session.
- Test runs follow the test-run policy: a task runs only its own tests; the full suites run once per PR (PR gate below).

## Review Focus

1. `config.py` computes paths with `Path(__file__).resolve().parent.parent` (lines 55 and 94). One level deeper they would point at `backend/` instead of the repo root and silently move the backup marker. T300 pins both.
2. A shim written as `from .core.x import *` breaks `monkeypatch.setattr(backend.ws, ...)`, module-level state (`database._pool`) and tests that read `backend/ws.py` as text. T300 to T303 use the alias and pin identity.
3. A stale allowlist line that nobody notices lets a violation come back. Both ratchets fail on stale and on new entries (T304, T305, T306).
4. The request-ID header must not be trusted blindly (log injection by CR/LF or length) and must not leak between concurrent requests (T307).
5. Logger names change with the move (`backend.ws` becomes `backend.core.ws`); tests that filter by logger name would go quiet. Checked in T302 (no test filters on these names today).

---

## 1. Architecture-test tool: `import-linter` (decision)

Measured on 2026-11-07 on this repo (Windows 11, Python 3.14 in a scratch venv, `import-linter` 2.16 with `grimp` 3.19, `pytest-archon` 0.0.7), against the real `backend` package (77 files, 283 dependencies):

| Criterion | import-linter | pytest-archon |
|-----------|---------------|---------------|
| Allowlist and ratchet | `ignore_imports` per contract plus `unmatched_ignore_imports_alerting = "error"`: a stale line **fails the run** (spiked: "No matches for ignored import ..."). New violations fail. Exact-match ratchet is native. | `.exclude(...)`; a stale exclude is silently accepted (spiked), so the "list only shrinks" half needs hand-written code. |
| Rule kinds | forbidden, independence, layers, acyclic siblings; external packages (`asyncpg`, `fastapi`, `httpx`) with `include_external_packages`; wildcards (`backend.routers.*`, `backend.modules.*.domain`); a wildcard that matches nothing is KEPT, so rules for modules that do not exist yet can be committed now. Function-level imports (the lazy `from ..ws import manager` in `hardware_reader`) are seen. | Fluent rules in test code; match/exclude by pattern; transitive by default. |
| Windows | Works (spiked on Windows 11). | Works. |
| Run time | 2.3 s warm, 18 s on the first cold run on the dev laptop; budget for CI: under 30 s (measure in T304, note in the PR). | about 1 s. |
| Maintenance | Config is data (TOML): an allowlist change is a reviewable diff of one line; callable from pytest through `importlinter.cli.lint_imports(config_filename=..., no_cache=True) -> int` and from a hook as `lint-imports`. Version 2.x. | Rules live in test code; version 0.0.x (pre-1.0). |

**Choice: import-linter.** The ratchet the programme depends on (new violations fail, finished steps must delete their lines) is built in; the alternative needs code that we would then maintain. Its weakness is that the config is a second place for an allowlist; SQL ownership and manifest completeness have no import-linter equivalent and are plain pytest with `allowlist.json` (decided by the spec). Both live in `backend/tests/architecture/`, so the kit's write scope and CI already cover them. A cold CI cache costs a few seconds; the `.import_linter_cache/` folder goes to `.gitignore`.

Config shape (TOML, comments allowed; `# until step N` marks when a line must be gone):

```toml
[tool.importlinter]
root_package = "backend"
include_external_packages = true
unmatched_ignore_imports_alerting = "error"

[[tool.importlinter.contracts]]
name = "legacy shims are not imported by production code"
type = "forbidden"
source_modules = ["backend.routers", "backend.fire", "backend.hardware_reader", "backend.simulation", "backend.main", "backend.db"]
forbidden_modules = ["backend.database", "backend.config", "backend.json_columns", "backend.ws"]
allow_indirect_imports = true
ignore_imports = [
    "backend.routers.groups -> backend.database",   # until step 4
]
```

Contracts committed in T304 (all with `allow_indirect_imports = true` except independence): `kernel imports no module` (`backend.core` must not import `routers`, `fire`, `hardware_reader`, `simulation`, `main`, `modules`; zero violations), `legacy shims are not imported by production code` (above; about 30 lines), `fire internals are private` (only `backend.fire` and `backend.routers.fire` import `backend.fire`; lines for `main`, `devices`, `settings`, `users`, until steps 1, 2 and 4), `routers are independent` (independence over `backend.routers.*`; zero), `domain is pure` (`backend.modules.*.domain` forbids `asyncpg`, `httpx`, `fastapi`, `backend.modules.*.infrastructure`; matches nothing today). From step 1 each new module adds its own `module boundary: <name>` contract (others may import only its `api`); T305 checks that every folder under `backend/modules/` has one.

Frontend: `dependency-cruiser` exact-pinned, driven from `src/architecture.test.js` through its `cruise()` API; allowlist in `src/architecture.allowlist.json` (T306).

## 2. Move map and importers (as of `cdc8f51`, from `git grep`)

Command to regenerate: `git grep -nE "(from|import) +(backend\.)?\.*(database|json_columns|config|auth|ws)\b" -- "*.py"` (the table was built from it plus the `from . import` forms).

| Old path | New path | Old path becomes | Production importers (not edited in step 0) | Test importers (unchanged unless noted) |
|----------|----------|------------------|---------------------------------------------|------------------------------------------|
| `backend/config.py` | `backend/core/config.py` | alias of the new module | `database.py`, `ws.py`, `auth.py`, `main.py:15`, `db/migrate.py:240,298,370` (lazy), `hardware_reader/hid_reader.py:40` and `reader.py:46,57` (lazy), `routers/{auth,locations,tiles,weather}.py` | 13 files: `conftest.py:118`, `script_env.py`, `modules/tracking/test_locations_{api,db}.py`, `test_auth_unit`, `test_b47`, `test_b51`, `test_backup_marker`, `test_db_host`, `test_api_weather:108`, `test_migrate_backup_guard`, `test_migrate_lock_timeout`, `test_restore` |
| `backend/database.py` | `backend/core/database.py` | alias | `auth.py:11`, `main.py:17`, `fire/{poller,service}.py`, `simulation.py:37`, `routers/{auth,devices,export,fire,groups,locations,settings,test,users}.py` | 8 files: `conftest.py`, `test_api_auth`, `test_api_fire_alerts:157`, `test_api_fire_read`, `test_api_settings`, `test_b47`, `test_b49`, `test_b51` |
| `backend/json_columns.py` | `backend/core/json_columns.py` | alias | `routers/{groups,locations,users}.py` | `test_b50.py` |
| `backend/ws.py` | `backend/core/ws.py` | alias | `main.py:21`, `routers/ws.py:3`, `hardware_reader/hid_reader.py:46` and `reader.py:39` (lazy) | `modules/core/test_live_ws.py`, `test_b51`, `test_fire_service`, `test_ws_forward`; **`test_smoke_script.py:444` reads the file text: path becomes `backend/core/ws.py`** |
| `backend/auth.py` (token part) | `backend/core/auth.py`: `ALGORITHM`, `create_access_token`, `create_refresh_token`, `decode_refresh_token` | `backend/auth.py` stays, re-exports those four; `hash_password`, `verify_password`, `oauth2_scheme`, `get_current_user`, `require_role` stay until `identity` (step 5) | `routers/auth.py:8` | `conftest.py`, `test_api_auth`, `test_auth_unit`, `test_b47`, `test_b51` |
| `main.py`, `db/migrate.py`, `version.py` | stay | not re-exports | external contracts: `uvicorn backend.main:app`, `python -m backend.db.migrate`, `sed` on `APP_VERSION` in `ci.yml` and `release.yml` | |

Outside the Python tree: `README.md` lines 391 to 417 draw the file tree (owner-written, proposal only); `Dockerfile`s copy the whole `backend/` folder, so `backend/core/` ships without edits; no script or workflow names the moved files.

The shim (identical in all four whole-module moves; shown once, used by T300 to T302):

```python
"""Old import path of backend.core.<name>, kept until step 5 (modular-monolith.md section 9)."""
import sys

from .core import <name> as _impl

sys.modules[__name__] = _impl   # the old name IS the new module: patches and module state stay shared
```

## 3. Task order and PRs

| PR | Task | Content | Reviewers (kit gate) | Hardware / smoke |
|----|------|---------|----------------------|------------------|
| 0 | this plan | docs only | task-reviewer + breaker on the plan before hand-over | none |
| 1 | T300 | `core/` package, `config` | breaker + security-reviewer | smoke |
| 2 | T301 | `database`, `json_columns` | breaker + security-reviewer (`database.py` is on the kit list) | smoke |
| 3 | T302 | `ws` | breaker + security-reviewer | smoke |
| 4 | T303 | token functions of `auth` | breaker + security-reviewer | smoke |
| 5 | T304 | backend guards: import-linter, ratchet, allowlist | breaker + security-reviewer (`requirements.txt`) | smoke |
| 6 | T305 | SQL-ownership scan, manifest contract | breaker | smoke |
| 7 | T306 | frontend guards | breaker + security-reviewer (`package.json`, lock file) | smoke |
| 8 | T307 | request-ID middleware | breaker + security-reviewer (`main.py`) | smoke |

Order is safe because T300 to T303 each stand alone (a leaf first: `config`, then what imports it), the guards come after the moves so the shim contract has real modules to point at, and T307 is last and detachable. `ef-migration-reviewer`: not required, step 0 has no migration and does not touch `backend/db/`. Hardware validation: not required, no file in `hardware_reader/` changes; the lazy `from ..ws import manager` keeps working through the alias.

**PR gate (every PR):** full backend suite, `cd frontend; npm test; npm run build` when the PR touches the frontend, `python tools/smoke.py` (see `docs/SMOKE.md`) with the PASS lines pasted into the PR body, then breaker and, where the table says so, security-reviewer on the head commit; `gh pr create` is run by the human with `--body-file`.

## 4. Allowlist and ratchet

- **Generation (once, in T304 and T305):** import violations come from running the contracts with empty `ignore_imports` (`.venv\Scripts\python backend\tests\architecture\regen.py --print-violations` prints `a -> b` lines grouped by contract, sorted, without line numbers); SQL violations come from the scanner (`file`, `table`, `verb`); frontend ones from the cruiser output. Each entry gets `until: step N` from the provisional module map (`backend/tests/architecture/module_map.py`: file to future module, module to step 1 to 5).
- **New violations fail:** the contracts and scanners run in the normal suites; anything not in the allowlist is red.
- **Stale entries fail:** import-linter errors on an unmatched ignore line; the JSON ratchets compare the scanned set to the file with equality, and the failure message says "delete this line".
- **Growth fails:** `test_allowlist_never_grows` compares the number of entries with the merge base (`ARCH_BASE_REF`, else `upstream/develop`, else `origin/develop`) and fails when the count rose; with no resolvable base (CI shallow clone) it skips with a visible reason. A justified addition needs a deliberate, reviewed edit of the test, never of the data alone. Wildcards in `ignore_imports` are refused by a test.
- **Shrink tooling:** `regen.py --remove-stale` deletes stale lines; there is no command that adds one.
- **End state:** `completed_step` in `allowlist.json` is bumped by each step; at 5 a test requires an empty allowlist and an empty shim list.

## 5. Risks and rollback

| Risk | Mitigation |
|------|------------|
| `Path(__file__)` depth in `config.py` | `parents[2]`; two tests (T300) |
| Shim breaks patches, state, text-reading tests | `sys.modules` alias; identity tests; one path edit in `test_smoke_script.py` |
| Logger names change (`backend.ws` to `backend.core.ws`) | grep found no test or script filtering on them; log lines differ only in the name; stated in the PR body |
| Parallel branches add imports of old paths | shims stay until step 5; the shim contract lists them, so they show up as growth, not breakage |
| Two PRs edit the same allowlist lines | one entry per line, sorted; `regen.py --remove-stale` resolves conflicts |
| import-linter cold run slow in CI | measured in T304; if above 30 s the architecture test gets a module-level `pytest.mark` and the contracts also run in the PR gate |
| Kit globs for security review do not cover `backend/core/**` | proposal in section 6; until accepted, every PR of this plan lists core files in its body |
| bee-dev gets a broken image | smoke gate before every PR; a bad merge is undone with `git revert -m 1 <merge>` and `deploy-develop.yml` redeploys |

**Rollback:** every PR is additive plus `git mv`; there is no schema or data change, so `git revert -m 1 <merge commit>` of the newest PR is complete. Reverting T300 requires reverting T301 to T303 first (they import `backend.core`). T304 to T307 can be reverted in any order. Field laptops are untouched until a release.

## 6. Open to the owner and hand-offs

1. Accept `import-linter` as the backend architecture tool and `dependency-cruiser` on the frontend (new dev dependencies; `pytest` already ships in `requirements.txt`, so the tool goes there too and the image grows by a few MB).
2. Request-ID middleware in step 0 (T307) or in step 4: decided for step 0, last PR, detachable (reasons in T307). It adds one response header and a `[request_id]` field to our log lines; if the owner wants literally zero visible change, drop T307 and the same task moves to step 4 unchanged.
3. `ci.yml` has no full git history on PRs, so `test_allowlist_never_grows` skips there; `fetch-depth: 0` on the backend job would enforce it in CI (workflow file: owner's call).
4. `README.md` file tree (lines 391 to 417) needs `core/` after T300 to T303 (owner-written).
5. To the architecture agent (text proposals, not edited here): modular-monolith.md 3.1 and 9 (`core/` not `platform/`; `migrate.py`, `version.py` stay), section 8 (tool = import-linter), ADR 19 (tool decision; note: `## DecisionGWIS` is still in `0019-architecture-tests.md` on `develop`, and `test_architecture_docs.py` checks only ADR 18).
6. To Kiril (kit): add `bee-with-me/backend/core/**` to `securityCriticalPaths` in `.claude/hooks/config.json`.
7. The programme spec lives in the workspace kit, outside this repo; say whether it should be added under `docs/` in the owner's repo.
8. Still open from the spec: tile-server and `SelectOfflineMap` belong to `maps` (step 5) and are untouched; RSSI/SNR fields in `BeeFrame`/`RepeaterFrame` are untouched.

---

### Task 300: `backend/core/` package and `config`

**risk:** security
**owner:** implementer
**Files:**
- Create: `backend/core/__init__.py` (docstring only)
- Move: `backend/config.py` to `backend/core/config.py` (`git mv`)
- Create: `backend/config.py` (shim, section 2)
- Create: `backend/tests/modules/core/test_core_kernel.py`

**Interfaces:**
- Produces: `backend.core.config.Settings`, `settings`, `KNOWN_ROLES`; `backend.config is backend.core.config`.

- [ ] **Step 1: Write the failing tests** in `test_core_kernel.py`, each tagged `T300`, with `REPO = Path(__file__).resolve().parents[4]`:
  `test_kernel_package_is_core_not_platform` (`importlib.util.find_spec('backend.core')` is not None; `not (REPO/'backend'/'platform').exists()`; a subprocess `[sys.executable, '-c', 'import platform; print(platform.__file__)']` run with `cwd=REPO/'backend'` prints a path outside `backend/`);
  `test_config_old_path_is_the_new_module` (`import backend.config as old, backend.core.config as new`; `old is new`; `old.settings is new.settings`);
  `test_backup_marker_default_is_under_the_repo_root` (`monkeypatch.delenv('BACKUP_MARKER_PATH', raising=False)`; `Settings(_env_file=None).backup_marker_path == REPO/'data'/'backups'/'last-backup.json'`);
  `test_relative_marker_path_resolves_against_the_repo_root` (`Settings(_env_file=None, backup_marker_path=Path('x/y.json')).backup_marker_path == REPO/'x'/'y.json'`).
- [ ] **Step 2: Run, expect FAIL** (`ModuleNotFoundError: backend.core`). Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\core\test_core_kernel.py -q`. Expected: FAIL.
- [ ] **Step 3: Move and fix.** `git mv backend/config.py backend/core/config.py`; in the moved file replace both `Path(__file__).resolve().parent.parent` with `Path(__file__).resolve().parents[2]`; write the shim with `<name>` = `config`. No other line changes.
- [ ] **Step 4: Run the new tests and the config-heavy existing ones.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\core\test_core_kernel.py backend\tests\test_db_host.py backend\tests\test_backup_marker.py backend\tests\test_migrate_backup_guard.py backend\tests\test_b47.py -q`. Expected: PASS.
- [ ] **Step 5: Commit** `refactor(core): T300 move config to backend/core behind an alias`.

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\core\test_core_kernel.py backend\tests\test_db_host.py backend\tests\test_backup_marker.py backend\tests\test_migrate_backup_guard.py backend\tests\test_b47.py -q`

### Task 301: `database` and `json_columns`

**risk:** security
**owner:** implementer
**Files:**
- Move: `backend/database.py` to `backend/core/database.py`; `backend/json_columns.py` to `backend/core/json_columns.py`
- Create: `backend/database.py`, `backend/json_columns.py` (shims)
- Modify: `backend/tests/modules/core/test_core_kernel.py`

**Interfaces:**
- Consumes: `backend.core.config.settings` (T300).
- Produces: `backend.core.database.{init_pool, close_pool, get_pool, get_conn}`, `backend.core.json_columns.decode_json_columns`; old names are the same module objects.

- [ ] **Step 1: Write failing tests** tagged `T301`: `test_database_old_path_is_the_new_module`, `test_json_columns_old_path_is_the_new_module` (identity as in T300); `test_pool_state_is_shared_through_the_old_path` (set `backend.core.database._pool = sentinel` with `monkeypatch.setattr`; `backend.database.get_pool() is sentinel`).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\core\test_core_kernel.py -q --task T301`. Expected: FAIL.
- [ ] **Step 3: Move both files** with `git mv`; in `core/database.py` the import line stays `from .config import settings` (resolves to `core.config` now); write both shims.
- [ ] **Step 4: Run** the T301 tests plus `test_b50.py`, `test_api_auth.py`, `test_api_settings.py`. Expected: PASS.
- [ ] **Step 5: Commit** `refactor(core): T301 move database and json_columns behind aliases`.

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\core\test_core_kernel.py backend\tests\test_b50.py backend\tests\test_api_auth.py backend\tests\test_api_settings.py -q`

### Task 302: `ws` (live channel, as it is)

**risk:** security
**owner:** implementer
**Files:**
- Move: `backend/ws.py` to `backend/core/ws.py`
- Create: `backend/ws.py` (shim)
- Modify: `backend/tests/test_smoke_script.py:444` (path only), `backend/tests/modules/core/test_core_kernel.py`

**Interfaces:**
- Consumes: `backend.core.config.settings`.
- Produces: `backend.core.ws.{manager, WSManager, FORWARDED_CHANNELS, RECONNECT_DELAY, HEALTHCHECK_INTERVAL}`; `routers/ws.py` and `hardware_reader` keep `from ..ws import manager`.

- [ ] **Step 1: Write failing tests** tagged `T302`: `test_ws_old_path_is_the_new_module`; `test_forwarded_channels_are_unchanged` (the exact tuple `('location_update', 'sos_alert', 'fire_data_updated', 'fire_alert', 'fire_alert_repeat', 'fire_alert_updated', 'fire_zones_updated')`); `test_core_ws_has_no_auth_or_origin_hook` (source of `backend/core/ws.py` contains neither `Origin` nor `jwt`, pinning "no behaviour change").
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\core\test_core_kernel.py -q --task T302`. Expected: FAIL.
- [ ] **Step 3: Move and shim.** `git mv`, shim with `<name>` = `ws`; change `ROOT / 'backend/ws.py'` to `ROOT / 'backend/core/ws.py'` in `test_smoke_script.py`.
- [ ] **Step 4: Run** the live-channel suites. Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\core backend\tests\test_ws_forward.py backend\tests\test_fire_service.py backend\tests\test_b51.py backend\tests\test_smoke_script.py -q`. Expected: PASS.
- [ ] **Step 5: Commit** `refactor(core): T302 move ws to backend/core behind an alias`.

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\core backend\tests\test_ws_forward.py backend\tests\test_fire_service.py backend\tests\test_b51.py backend\tests\test_smoke_script.py -q`

### Task 303: token functions of `auth`

**risk:** security
**owner:** implementer
**Files:**
- Create: `backend/core/auth.py`
- Modify: `backend/auth.py` (remove the four definitions, import them from `.core.auth`)
- Modify: `backend/tests/modules/core/test_core_kernel.py`

**Interfaces:**
- Consumes: `backend.core.config.settings`.
- Produces: `backend.core.auth.ALGORITHM = 'HS256'`, `create_access_token(user_id: str, role: str) -> str`, `create_refresh_token(user_id: str, role: str) -> str`, `decode_refresh_token(token: str) -> dict` (same claims `sub`, `role`, `typ`, `exp` and same 401 detail text). `backend.auth` re-exports them next to the untouched `hash_password`, `verify_password`, `oauth2_scheme`, `get_current_user`, `require_role`.

- [ ] **Step 1: Write failing tests** tagged `T303`: `test_token_functions_are_the_same_objects` (for the four names `getattr(backend.auth, n) is getattr(backend.core.auth, n)`); `test_core_auth_imports_only_stdlib_jose_fastapi_and_config` (parse `backend/core/auth.py` with `ast`; imported top-level names are a subset of `{'datetime', 'fastapi', 'jose', 'typing'}` plus the relative import of `.config`; in particular no `database` and no `asyncpg`, so the kernel never touches the `users` table).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\core\test_core_kernel.py -q --task T303`. Expected: FAIL.
- [ ] **Step 3: Extract** the four definitions unchanged into `core/auth.py`; `backend/auth.py` imports `ALGORITHM, create_access_token, create_refresh_token, decode_refresh_token` from `.core.auth` (marked as intentional re-exports) and keeps using `ALGORITHM` inside `get_current_user`.
- [ ] **Step 4: Run** token and auth suites. Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\core\test_core_kernel.py backend\tests\test_auth_unit.py backend\tests\test_api_auth.py backend\tests\test_b47.py backend\tests\test_b51.py -q`. Expected: PASS.
- [ ] **Step 5: Commit** `refactor(core): T303 move token functions of auth to backend/core`.

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\core\test_core_kernel.py backend\tests\test_auth_unit.py backend\tests\test_api_auth.py backend\tests\test_b47.py backend\tests\test_b51.py -q`

### Task 304: backend architecture guards (import-linter, ratchet)

**risk:** security
**owner:** implementer
**Files:**
- Modify: `backend/requirements.txt` (add `import-linter>=2.16,<3`), `.gitignore` (add `.import_linter_cache/`)
- Create: `backend/tests/architecture/__init__.py`, `importlinter.toml`, `module_map.py`, `regen.py`, `test_import_contracts.py`, `test_ratchet.py`

**Interfaces:**
- Produces: `module_map.MODULE_OF_FILE: dict[str, tuple[str, ...]]` (repo-relative path or `dir/**` to the future module(s); e.g. `backend/routers/users.py` to `('people',)`, `backend/routers/locations.py` to `('tracking', 'sos')`, `backend/hardware_reader/**` to `('gateway',)`, `backend/fire/**` and `backend/routers/fire.py` to `('fire',)`, `backend/core/**` and `backend/db/**` to `('core',)`, `backend/main.py` to `()`); `module_map.STEP_OF_MODULE = {'settings': 1, 'fire': 2, 'tracking': 3, 'sos': 3, 'gateway': 3, 'devices': 4, 'teams': 4, 'people': 4, 'identity': 5, 'reporting': 5, 'maps': 5, 'weather': 5, 'simulation': 5}`; `regen.main(argv: list[str]) -> int` with `--print-violations` and `--remove-stale`; `test_ratchet.count_entries(path: Path) -> int`.

- [ ] **Step 1: Write the failing tests** tagged `T304`: in `test_import_contracts.py`, `test_real_code_satisfies_all_contracts` (`monkeypatch.chdir(REPO)`; `importlinter.cli.lint_imports(config_filename=str(TOML), no_cache=True) == 0`); `test_every_contract_bites` (parametrised over the contract names in the TOML; builds a toy package in `tmp_path` by replacing `backend` with `toy` in the TOML text, empties every `ignore_imports`, writes one violating import per contract, and expects a non-zero result; the contract `domain is pure` is fed `toy/modules/x/domain.py` importing `asyncpg`); `test_a_stale_allowlist_line_fails` (append a bogus `a -> b` line to a copy of the TOML, expect non-zero). In `test_ratchet.py`: `test_no_wildcards_in_ignore_imports`, `test_allowlist_never_grows` (base resolution and skip rules in section 4; compares `count_entries` of HEAD and base), `test_allowlist_lines_carry_an_until_step` (every `ignore_imports` line has a comment `# until step N` with N from 1 to 5).
- [ ] **Step 2: Run, expect FAIL** (`ModuleNotFoundError: importlinter` until installed, then missing TOML). Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\architecture -q --task T304`. Expected: FAIL.
- [ ] **Step 3: Install and write the config.** `.venv\Scripts\python -m pip install "import-linter>=2.16,<3"`; write `importlinter.toml` with the five contracts of section 1 and empty ignore lists; `regen.py --print-violations` runs `lint_imports` on that config and prints `source -> target` lines sorted and without line numbers, with `until step N` taken from `module_map` by the importing file; paste the printed lines into the matching `ignore_imports` lists with their comments. Expected population: about 30 shim lines, the fire-internals lines for `main`, `devices`, `settings`, `users` and `routers.fire`.
- [ ] **Step 4: Run** `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\architecture -q --task T304`. Expected: PASS. Record the wall time of the first (cold) and second run in the PR body.
- [ ] **Step 5: Commit** `test(architecture): T304 pin import-linter with a ratchet allowlist`.

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\architecture -q --task T304`

### Task 305: SQL-ownership scan and manifest contract

**risk:** normal
**owner:** implementer
**Files:**
- Create: `backend/core/modules.py`, `backend/modules/__init__.py`
- Create: `backend/tests/architecture/sql_scan.py`, `allowlist.json`, `rules.py`, `test_sql_ownership.py`, `test_manifest.py`

**Interfaces:**
- Produces in `core/modules.py`: `@dataclass(frozen=True) class ModuleManifest` with `name: str`, `owns_tables: tuple[str, ...] = ()`, `reads_tables: tuple[str, ...] = ()`, `depends_on: tuple[str, ...] = ()`, `router: APIRouter | None = None`, `tasks: tuple[Callable[[], Awaitable[None]], ...] = ()`, `live_messages: tuple[str, ...] = ()`, `subscriptions: tuple[tuple[str, Callable], ...] = ()`; and `validate_manifest(m: ModuleManifest) -> list[str]` (empty list means valid).
- Produces in `backend/modules/__init__.py`: `MODULES: tuple[ModuleManifest, ...] = ()`; a module is "a folder plus one line here". `main.py` does not read it yet (wired in step 1, when the first module exists).
- Produces in `rules.py`: `TABLE_OWNER` (`users` to `people`; `groups`, `user_groups` to `teams`; `devices` to `devices`; `location_events`, `repeater_events` to `tracking`; `sos_alerts` to `sos`; `fire_hotspots`, `fire_burnt_areas`, `fire_alerts`, `fire_suppression_zones` to `fire`; `settings` to `settings`; `schema_migrations` to `core`) and `ALLOWED_EDGES` (the graph of modular-monolith.md 4.2 plus `fire -> people`, `simulation -> people, devices, teams` from the spec).
- Produces in `sql_scan.py`: `scan_writes(root: Path) -> set[tuple[str, str, str]]` of `(repo-relative file, table, verb)` found by `INSERT\s+INTO\s+(\w+)`, `UPDATE\s+(\w+)\s+SET`, `DELETE\s+FROM\s+(\w+)` (case-insensitive, multi-line) in production `.py` files (not under `tests/`); `scan_sql_outside_infrastructure(root: Path) -> set[tuple[str, str]]` for `conn.execute|fetch|fetchrow|fetchval` calls under `backend/modules/` outside `infrastructure/`.

- [ ] **Step 1: Write the failing tests** tagged `T305`: `test_real_writes_match_the_allowlist_exactly` (violations = scanned writes whose table owner is not in `MODULE_OF_FILE` for that file; equality with `allowlist.json["sql_writes"]`; the failure message lists "new:" and "stale, delete:" separately; `schema_migrations` in `db/migrate.py` and `settings`-owned writes in `routers/settings.py` are not violations); `test_scanner_finds_multiline_and_lowercase_sql` (tmp file with `"""\n  update  devices\n  set x = 1"""` yields `('devices', 'UPDATE')`); `test_scan_sql_outside_infrastructure_bites_on_a_toy_tree`; in `test_manifest.py`: `test_validate_manifest_rules` (name must match `^[a-z][a-z_]*$` and the folder; an owned table must be in `TABLE_OWNER` for that name; `depends_on` names exist and only edges in `ALLOWED_EDGES`; live message names unique across modules), `test_graph_has_no_cycles` (fixture manifests with a cycle fail), `test_real_module_list_is_complete` (every `backend/modules/<x>/module.py` appears in `MODULES` and has a contract named `module boundary: <x>` in the TOML; vacuous today, proven by a tmp tree), `test_allowlist_json_never_grows` (reuses the T304 base logic).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\architecture -q --task T305`. Expected: FAIL.
- [ ] **Step 3: Implement** the signatures above. Seed `allowlist.json` from the scanner with `{"completed_step": 0, "sql_writes": [{"file", "table", "verb", "until"}]}`; the expected set is the cross-module writes of spec section 4: `routers/devices.py` into `sos_alerts`, `location_events`, `repeater_events`; `routers/users.py` and `routers/test.py` and `simulation.py` into `location_events`, `sos_alerts` (and `users`, `devices`, `groups`, `user_groups` for `simulation.py`); `hardware_reader/reader.py` into `location_events`, `sos_alerts`, `repeater_events`; `main.py` into `users`, `location_events`; and the `UPDATE` statements the multi-line scan finds.
- [ ] **Step 4: Run** `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\architecture -q`. Expected: PASS.
- [ ] **Step 5: Commit** `test(architecture): T305 SQL ownership ratchet and module manifest contract`.

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\architecture -q --task T305`

### Task 306: frontend architecture guard

**risk:** security
**owner:** implementer (if a hook routes a path to the `frontend-designer`, dispatch it with this task text; the files here are plain `.js` and `.json`)
**Files:**
- Modify: `frontend/package.json` (devDependency `dependency-cruiser`, exact version), `frontend/package-lock.json` (via `npm install --save-dev --save-exact dependency-cruiser@<version>`)
- Create: `frontend/.dependency-cruiser.cjs`, `frontend/src/architecture.test.js`, `frontend/src/architecture.allowlist.json`, `frontend/src/platform/manifest.js`

**Interfaces:**
- Produces in `manifest.js`: `validateManifest(m) -> string[]` for the fields `name`, `routes`, `nav`, `mapLayers`, `panels`, `banners`, `liveHandlers`, `i18n` (`{en, bg}`), `depends` (modular-monolith.md 3.2 and 7); empty array means valid. Nothing imports it yet.
- Rules in `.dependency-cruiser.cjs` (names are stable keys of the allowlist): `lib-is-pure` (`src/lib` imports none of `src/(api|stores|composables|components|views|router)` and not `vue` or `pinia`), `no-upward-layers` (`api`, `stores`, `composables`, `lib` do not import `components` or `views`; `components` do not import `views`), `no-circular`, `platform-imports-no-module`, `modules-only-through-index` (a file in `src/modules/a` imports from `src/modules/b` only `index.js`).

- [ ] **Step 1: Write the failing tests** in `architecture.test.js`, each `[T306]`: `it('real sources match the allowlist exactly [T306]')` (cruise `src` from `frontend/`, keep violations of severity error, key `rule|from|to` with forward slashes; equality with `architecture.allowlist.json`, message lists new and stale keys); `it('each rule bites on a fixture tree [T306]')` (write a tiny tree under `os.tmpdir()` with one violation per rule and cruise it with the same rule set); `it('manifest validator accepts a complete manifest and names each missing field [T306]')`; `it('allowlist never grows against the merge base [T306]')` (same git rule as T304, skipped with a message when no base ref resolves).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/architecture.test.js`. Expected: FAIL.
- [ ] **Step 3: Install and configure.** `npm view dependency-cruiser version` then `npm install --save-dev --save-exact dependency-cruiser@<that version>`; write the rule file with `tsConfig` absent and `doNotFollow: node_modules`; `cruise()` is called with `baseDir` set to `frontend` and rules from the config. Seed `architecture.allowlist.json` from the first run (`{"completed_step": 0, "violations": ["rule|from|to"]}`), each key sorted; no key for the vacuous module rules.
- [ ] **Step 4: Run** `cd bee-with-me\frontend; npm test; npm run build`. Expected: PASS (all vitest files and a clean build).
- [ ] **Step 5: Commit** `test(architecture): T306 dependency-cruiser guard with a ratchet allowlist`.

dod:
- `cd bee-with-me\frontend; npm test -- src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`

### Task 307: request-ID middleware with correlation ID

**risk:** security
**owner:** implementer
**Files:**
- Create: `backend/core/request_id.py`
- Modify: `backend/main.py` (two additions: `app.add_middleware(RequestIdMiddleware)` next to the CORS registration, and the log format plus handler filter next to `logging.basicConfig`)
- Create: `backend/tests/modules/core/test_request_id.py`

**Decision (step 0, last PR, detachable).** Step 4 is already the heaviest PR (outbox, two migrations, three modules). The contextvar and log filter must exist before steps 1 to 3 write module code, so every module logs correlated from its first commit; the change is additive (a response header and a log field), covers no event yet, and `git revert` removes it alone. Events, outbox and inbox columns, and per-tick IDs for the poller and retention are added in step 4 on top of this API.

**Interfaces:**
- Produces: `REQUEST_ID_HEADER = 'X-Request-ID'`; `request_id_var: ContextVar[str]` (default `'-'`); `get_request_id() -> str`; `new_request_id() -> str` (32 lowercase hex); `accept_request_id(raw: str | None) -> str` (returns `raw` only when it matches `^[A-Za-z0-9._-]{1,64}$`, else a new ID); `class RequestIdMiddleware` (pure ASGI, `__init__(self, app)`, `async __call__(self, scope, receive, send)`; sets the var for `http` and `websocket` scopes, adds the response header on `http.response.start`, passes `lifespan` through, resets the var afterwards); `class RequestIdLogFilter(logging.Filter)` setting `record.request_id`; `use_request_id(value: str | None = None)` context manager for background ticks (used from step 4). Log format: `%(levelname)s:%(name)s:[%(request_id)s] %(message)s`.
- Known limit, pinned by a test: a response produced by the outermost server-error handler for an unhandled exception carries no header. Uvicorn's own loggers keep their format.

- [ ] **Step 1: Write the failing tests** tagged `T307`, with a small FastAPI app that has the middleware and a route that logs: `test_valid_incoming_id_is_echoed_and_logged` (header `abc-123` comes back and the log record has `request_id == 'abc-123'`); `test_missing_id_is_generated` (32 hex characters); `test_invalid_ids_are_replaced` (parametrised: `'a\r\nb'`, 65 characters, `'has space'`, empty string); `test_header_present_on_404_and_422`; `test_concurrent_requests_do_not_share_ids` (`asyncio.gather` of 20 requests through `httpx.AsyncClient(transport=ASGITransport(app))`, each echoes its own ID from the handler); `test_websocket_connection_still_works` (Starlette `TestClient.websocket_connect` echo route); `test_filter_defaults_to_dash_outside_a_request`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\core\test_request_id.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the interfaces; `main.py` registers the middleware (added after CORS so it is outermost of the two) and attaches `RequestIdLogFilter` to the root handlers right after `logging.basicConfig(level=logging.INFO, format=...)`. No other line of `main.py` changes.
- [ ] **Step 4: Run** the new tests and the app-level suites that import `main`. Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\core backend\tests\test_startup_migrations.py backend\tests\test_simulation.py backend\tests\test_scripts.py -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(core): T307 request-ID middleware and correlated log lines`.

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\core backend\tests\test_startup_migrations.py backend\tests\test_simulation.py backend\tests\test_scripts.py -q`
