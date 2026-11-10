# Vertical slices, step 1: the `settings` module (the template for every later module) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `settings` into the first vertical-slice module on both sides (`backend/modules/settings/`, `frontend/src/modules/settings/`), make `main.py` and the frontend router, navigation and i18n read a module list, and remove the `settings_router.after_change` wiring from `main.py`, with no change the operator can notice.

**Architecture:** The backend router file splits along the anatomy of modular-monolith.md 3.1 (`module.py`, `api.py`, `http.py`, `domain/`, `infrastructure/`); the old path `backend/routers/settings.py` stays as a `sys.modules` alias of the new `http` module, so every existing patch and import keeps working. `main.py` mounts routers and starts tasks from `backend.modules.MODULES` through two functions in `backend/core/modules.py`. The frontend gets a module list (`src/modules/index.js`) that the router, the navigation and the i18n dictionaries are assembled from; `settings` is its first entry. Debt that step 1 cannot remove (settings calling fire directly until the outbox of step 4) is carried as named allowlist lines.

**Tech Stack:** Python 3.11+, FastAPI, asyncpg, pydantic, import-linter (existing dev dependency), pytest; Vue 3, Pinia, vue-router 4, vue-i18n 11, vitest, dependency-cruiser (existing). No new dependency.

**Spec:** [`docs/superpowers/specs/2026-10-31-vertical-slices-programme-design.md`](../specs/2026-10-31-vertical-slices-programme-design.md) (section 5 "Step 1", sections 6 and 7), `Architecture/application/modular-monolith.md` sections 3, 4, 8, 9, ADR 17 (Accepted), ADR 19 (Proposed). Format and lessons: [`2026-11-07-vs-step0-kernel-and-guards.md`](2026-11-07-vs-step0-kernel-and-guards.md).

**Base:** `upstream/develop` at `2472543` (PR #103, T305 merged). Plan branch: `docs/vs-wave1-plans`. Execution branches: `feature/vs-1-<task>` off `develop`, one PR per task. Wave overview: [`2026-11-10-vs-wave1-overview.md`](2026-11-10-vs-wave1-overview.md).

## Global Constraints

- Base branch `upstream/develop`; PRs go to `develop`; merge conflicts are solved by merging `upstream/develop` into the feature branch, never by rebase or force-push.
- Kernel is `backend/core/` and `frontend/src/platform/`. `backend/main.py`, `backend/db/migrate.py`, `backend/version.py` do not move.
- Old import paths stay thin re-exports until step 5: backend = `sys.modules` alias (never `import *`); frontend = a file whose only statement is `export * from '<new path>'`.
- Behaviour does not change. The only visible differences are the logger name `backend.routers.settings` becoming `backend.modules.settings.http` and named routes on the frontend (`name: 'settings'`), both stated in the PR body.
- No WebSocket security work, no `fire_alert*` payload change, no schema change, no migration, no edit of `hardware_reader/*`, `data/`, `tiles/`, `backend/uploads/`, `.env`. Owner-written files (`README.md`, `CHANGELOG.md`, `todo.md`, `docs/PROTOCOL.md`, `.github/workflows/**`, `deploy/**`, `package-lock.json`) are not edited.
- Tests stay under `backend/tests/` and `frontend/src/**`. Existing tests stay green and unedited except import paths (the three known non-import edits are listed in section 5).
- Tags: pytest `@pytest.mark.Trait("Task", "T4xx")` (double quotes), vitest `it('... [T4xx]', ...)`. Commits: `type(scope): T4xx summary`, body ends with the Co-Authored-By line of the session.
- Frontend files `.vue` and `.css` are changed only by the `frontend-designer` agent (T404). `.js` files (router, i18n, stores, manifests, platform) are not routed.
- Test runs follow the test-run policy: a task runs its own DoD; the full suites run once per PR in the PR gate (section 3).

## Review Focus

1. A save that succeeded must not turn into a 500 because the reaction failed: the publisher that tells fire to re-evaluate catches and logs (T402, `test_publish_failure_does_not_fail_the_request`).
2. The alias of `backend.routers.settings` must be the `http` module itself; an `import *` shim would make `monkeypatch.setattr(settings_router, 'after_change', ...)` patch a copy and the 8 patches in `test_api_settings.py` would silently test nothing (T402, `test_old_router_path_is_the_module_http`).
3. An invalid or duplicated manifest must stop the start with a clear message, not mount half a module list (BP-03) (T400, `test_include_module_routers_refuses_an_invalid_list`).
4. A module task that crashes must be logged and all module tasks must be cancelled and awaited before the pool closes (T400, `test_start_and_stop_module_tasks`).
5. Two dictionaries defining the same i18n key must not white-screen the app at import and must not pass unnoticed: the merge never throws, a test fails on any collision or on an EN/BG key difference inside a module, and every PR that moves texts shows the same leaf-key count before and after (T403, T404).

---

## 1. The module template (applies to every later module)

### 1.1 Backend anatomy (`backend/modules/<name>/`)

| File | Holds | Rules checked by |
|------|-------|------------------|
| `__init__.py` | docstring only | |
| `module.py` | `manifest = ModuleManifest(name=..., owns_tables=..., reads_tables=..., depends_on=..., router=http.router, tasks=..., live_messages=..., subscriptions=...)` | `core.modules.validate_manifest`, `rules.check_manifests`, `rules.check_manifest_wiring` (T401) |
| `api.py` | the only entry point for other modules: event types, commands, read models | contract `module boundary: <name>` |
| `http.py` | the FastAPI `router`, dependencies, orchestration of one request (transaction boundaries). No SQL text | `sql_scan.scan_sql_outside_infrastructure` |
| `domain/` | pydantic models, dataclasses and rules. No `asyncpg`, `httpx`, `fastapi`, no `infrastructure` | contract `domain is pure` |
| `infrastructure/` | SQL (`repository.py`), external clients, the interim publisher | SQL-ownership scan |
| `tasks.py` | background coroutines listed in `manifest.tasks`; omitted when the module has none | `rules.check_manifest_wiring` |

One line in `backend/modules/registry.py` registers the module: `from .<name>.module import manifest as <name>_manifest` plus the name in the `MODULES` tuple. The alias matters: a name equal to the sub-package (`as settings`) would replace the attribute `backend.modules.settings` with the manifest and break `import backend.modules.settings.http` and every string patch target. `backend/modules/__init__.py` imports no module; it serves `MODULES` lazily (`__getattr__`), so `from backend.modules import MODULES` keeps working while importing `backend.modules.<name>.api` does not import every module's `http.py`. Without that, the allowed edge `fire -> settings.api` of step 2 would be an import cycle (`settings.http` imports `backend.fire` today). `main.py` is not edited by later modules: it mounts `m.router` for every manifest in list order and starts `m.tasks`.

### 1.2 Frontend anatomy (`frontend/src/modules/<name>/`)

`index.js` (the manifest: `name`, `routes`, `nav`, `mapLayers`, `panels`, `banners`, `liveHandlers`, `i18n`, `depends`; the map fields `toggle`, `popups`, `contextMenu` and the separate map entry file `map/index.js` are defined in the map-shell plan, section 1; a manifest never imports OpenLayers), `store.js`, `views/`, `components/`, `lib/` (pure: no api, no store, no vue, no pinia), `i18n/en.js` and `i18n/bg.js` (the module's own namespaces, including its `nav.<name>` label), tests next to the code. One line in `src/modules/index.js` registers the module. Routes carry an absolute `path` and a `name`; navigation items carry `order` (the static items use 10, 20, ... 80; a module takes the number of the item it replaces).

### 1.3 Moving a file and keeping the old import path

1. `git mv` the file (history follows), then repoint the imports inside the moved file.
2. List the remaining importers of the old path: `git grep -nE "<old dotted or relative path>" -- backend frontend/src`. Tests move with their code (frontend) or stay where they are (backend).
3. If a production file that does not move still imports the old path, leave a thin re-export there. Backend (the whole old module is the new one):
   ```python
   """Old import path of backend.modules.<name>.<file>, kept until step 5 (modular-monolith.md section 9)."""
   import sys

   from ..modules.<name> import <file> as _impl

   sys.modules[__name__] = _impl   # the old name IS the new module: patches and module state stay shared
   ```
   Frontend: `export * from '../modules/<name>/<file>.js'` as the only statement.
4. If no production importer is left, no shim: delete the old path.
5. Before relying on a frontend shim, check that no test mocks the old path (`git grep -n "vi.mock('[^']*<old file>" -- frontend/src` must print nothing): `vi.mock` of a re-export does not reach the real module.

### 1.4 Allowlist lines

- **Deleting:** run `.venv\Scripts\python backend\tests\architecture\regen.py --remove-stale` after the move; it deletes the lines that no longer match (the `# until step N` lines of the moved file). SQL rows in `allowlist.json` are deleted by hand; `test_real_writes_match_the_allowlist_exactly` prints `stale, delete:`. A deleted line that was an approved addition also loses its entry in `approved_additions.py` (`test_every_approval_is_still_in_its_file` says `delete this approval`). Then set `completed_step` in `backend/tests/architecture/allowlist.json` and in `frontend/src/architecture.allowlist.json` to the step number.
- **Adding (rare, reviewed):** an edge that a step cannot remove yet gets a new `ignore_imports` line with `# until step N` **and** an entry in `backend/tests/architecture/approved_additions.py` with the reason (T401). The growth test fails on any new line that is not approved, and on any approval whose line is gone.
- **New contract per module:** `module boundary: <name>` (type `forbidden`): `source_modules` = the legacy packages plus every other `backend.modules.<other>`; `forbidden_modules` = every child of `backend.modules.<name>` except `api`. A new module also adds itself to the `source_modules` of the existing boundary contracts; `rules.check_boundary_contracts` (T401) fails when one is missing.

### 1.5 What a module PR contains

Move, shims, manifest, one list line, allowlist shrink, `completed_step`, the module's own tests in `backend/tests/modules/<name>/` and next to the frontend code, the PR gate of section 3, and in the PR body: files moved, shims left, allowlist lines deleted and added (with reasons), logger names that changed.

## 2. File map and who else touches each file (as of `2472543`)

Commands used: `git grep -nE "routers(\.| import |/)settings|settings_router|after_change" -- backend tools`, `git grep -nE "(from|import\() *'[^']*(stores/settings|useSettings|settingsForm)" -- frontend/src`, `git branch -r --no-merged upstream/develop` with `git diff --name-only upstream/develop...<branch>`.

| File | This plan | Also read or written by |
|------|-----------|-------------------------|
| `backend/main.py` (hot) | T400 adds the loader calls; T402 removes lines 20, 181, 265 | every backend step until 5; `main` holds B62 and B67 edits that `develop` lacks (owner's reconcile); tests `test_b49`, `test_b51`, `test_simulation`, `test_startup_migrations`, `test_fire_anonymise`, `test_fire_poller`, `test_request_id`, `test_migrate_backup_guard` import it |
| `backend/core/modules.py` | T400 adds three functions | `backend/modules/__init__.py`, `backend/tests/architecture/{rules,test_manifest}.py` |
| `backend/modules/__init__.py`, new `backend/modules/registry.py` | T402: lazy `MODULES` in the first, the list with its first line in the second | every later backend module adds one import and one name to `registry.py` |
| `backend/tests/architecture/module_map.py` | T402 adds the key `'modules/registry.py': ('core',)` | steps 2 to 5 read it |
| `backend/routers/settings.py` | T402: becomes the alias | `backend/tests/conftest.py:19,33`, `backend/tests/test_api_settings.py` (8 `monkeypatch.setattr` calls on it), `backend/main.py` (until T402) |
| `backend/tests/architecture/importlinter.toml` (hot) | T401 widens two `source_modules`; T402 deletes 3 lines, adds 4 lines and one contract | every backend step |
| `backend/tests/architecture/allowlist.json` (hot) | T402 sets `completed_step` to 1 (no `settings` row exists) | every backend step |
| `backend/tests/architecture/{test_ratchet,test_sql_ownership,test_manifest,rules}.py` | T401 (approvals, wiring and boundary checks); T402 one path string in `test_sql_ownership.py:42-43` | steps 2 to 5 use them, do not edit them |
| `backend/tests/test_api_settings.py` | T402: one logger-name string (line 184) | none |
| `tools/smoke.py`, `backend/tests/test_smoke_script.py`, `docs/SMOKE.md` | T400 adds step g (`GET /api/settings`) | every PR's smoke gate |
| `frontend/src/router/index.js` (security-critical) | T403 assembles module routes; T404 deletes the `settings` line | plan 3 (T440 deletes three lines); `router/index.test.js` |
| `frontend/src/nav-config.js` | T403 adds `order` and the merge; T404 deletes the `settings` item | plan 3 (T440); `components/AppLayout.vue` |
| `frontend/src/i18n/en.js`, `bg.js` (hot) | T403 wraps the literal in the merge; T404 takes out `settings` (lines 221 to 346 of `en.js`) and `nav.settings` | plan 3 (T440 takes out `users`, `groups`, `devices`); 17 test files import `en.js` |
| `frontend/src/modules/index.js` | T403 creates it empty; T404 adds `settings` | plan 3 (T440 adds three lines); plan 2 reads it |
| `frontend/src/platform/registry.js` | T403 creates it | plan 3 reads it; plan 2 uses its own file `platform/map-shell/contributions.js` |
| `frontend/.dependency-cruiser.cjs` | T403 extends `lib-is-pure` to `modules/*/lib` | none in this wave |
| `frontend/src/views/SettingsView.vue` + 4 tests | T404 moves them | imports `stores/fire`, `components/{SuppressionZoneForm,TestModeCard,OfflineMapsCard}.vue`, `lib/fireErrors` (stay where they are) |
| `frontend/src/stores/settings.js` + test | T404 moves it, leaves a re-export | `views/MapView.vue:326`, `views/MapView.test.js:29` (through the re-export) |
| `frontend/src/composables/useSettings.js` + test | T404 moves it, leaves a re-export | `composables/useMap.js:23`, `components/OfflineMapsCard.vue` (through the re-export) |
| `frontend/src/lib/settingsForm.js` + test | T404 moves it, no re-export (both importers move too) | none |

Not touched by this plan: `MapView.vue`, `useMap.js`, `AppLayout.vue`, `platform/manifest.js`, `architecture.test.js`, `backend/fire/**`, `backend/tests/conftest.py`.

## 3. Task order, PRs, reviewers, parallel work

| PR | Task | Content | Reviewers | Smoke |
|----|------|---------|-----------|-------|
| 1 | T400 | module loader in `core/modules.py` and `main.py`; smoke step for `/api/settings` | breaker + security-reviewer (`main.py`, `core/**`) | yes |
| 2 | T401 | architecture guards for the first module | breaker | yes |
| 3 | T402 | backend `settings` module | breaker + security-reviewer (`routers/**`, `main.py`) | yes |
| 4 | T403 | frontend module assembly (empty list) | breaker + security-reviewer (`src/router/**`) | yes |
| 5 | T404 | frontend `settings` module (`frontend-designer`) | breaker + security-reviewer (`src/router/**`) | yes |

**Inside the plan.** T400, T401 and T403 touch disjoint files and run in parallel. T402 needs T400 and T401 merged (it edits `main.py` after T400 and `importlinter.toml` after T401). T404 needs T403 merged. T402 and T404 are independent of each other (backend and frontend of the same module) and run in parallel; the design allows one PR for both, this plan keeps two because the reviewers and the owners differ.

**Against the other two plans.** Plan 2 (map-shell) shares no file with T400 to T403; its last task (T427, HQ layer) needs T404. Plan 3 needs T403 merged before its first task and edits the same four shared files as T404:

| File pair | Who | Conflict and resolution |
|-----------|-----|-------------------------|
| `src/modules/index.js` | T404 and T440 | adjacent lines; keep both, alphabetical |
| `src/router/index.js`, `src/nav-config.js` | T404 and T440 | different, non-adjacent lines (`settings` against `users`, `groups`, `devices`); merges cleanly; if not, keep both deletions |
| `src/i18n/en.js`, `bg.js` | T404 and T440 | different namespaces; the `nav` block lines are not adjacent; keep both deletions; the collision and parity tests (T403) and the before/after leaf count in the PR body show nothing was lost |

Merge T404 before T440 where possible; the later branch merges `upstream/develop` and reruns its DoD.

**PR gate (every PR), in this order:** (1) the task's DoD; (2) the full backend suite `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests -q` when a backend file changed, and `cd bee-with-me\frontend; npm test; npm run build` when a frontend file changed; (3) `python tools/smoke.py` (see `docs/SMOKE.md`), PASS lines pasted into the PR body; from T400 on that includes step g, which is the only smoke check that exercises this module; (4) `breaker` and, where the table says so, `security-reviewer` on the head commit until both end with `VERDICT: PASS`; (5) for T404: remind the maintainer to run the impeccable detector on the moved view; (6) `gh pr create` is run by the human with `--body-file`. No hardware validation (no file in `hardware_reader/` changes) and no `ef-migration-reviewer` (no migration).

## 4. Risks, rollback, not verified

| Risk | Mitigation |
|------|------------|
| The default-wired `after_change` now calls fire's `request_evaluation` in every test that saves settings | it only sets an `asyncio.Event` and never raises; `test_api_settings.py` passes unedited (T402 DoD) |
| Router order changes the order of tags in `/docs` | the loader call sits exactly where `settings_router` was mounted; `test_settings_routes_keep_their_place` pins it |
| The logger name changes | one test string edited (section 5); stated in the PR body |
| A later branch still imports `backend.routers.settings` | the alias keeps it working until step 5; the boundary contract lists exactly that one edge |
| Import cycle through the module list (`settings.http` imports `backend.auth` and `backend.fire`; step 2 lets fire import `settings.api`) | the list lives in `backend/modules/registry.py` and `backend/modules/__init__.py` loads it only when `MODULES` is asked for; `test_importing_the_api_does_not_import_http` and `test_importing_the_old_path_first_works` run in fresh interpreters |
| `i18n/en.js` evaluated in 17 test files now also loads module dictionaries | it loads only `modules/*/i18n/{en,bg}.js` through `import.meta.glob`, never a manifest, a store or a component |
| bee-dev gets a broken image | smoke gate before every PR; a bad merge is undone with `git revert -m 1 <merge>` |
| The owner merges `main` into `develop` (B62, B67 touch `main.py`) while T400 or T402 is open | merge `upstream/develop` into the branch; T400 and T402 add or remove whole lines next to the router list and inside `lifespan`, nowhere near those fixes |

**Rollback.** No schema or data change: `git revert -m 1 <merge commit>`, newest first (T404, T403, T402, T401, T400). T402 and T404 are independent of each other and can be reverted alone. Field laptops are untouched until a release.

**Not verified while planning (the executor checks it in the named step):**
- import-linter behaviour for the new `module boundary: settings` contract (forbidden sub-packages, the alias edge `backend.routers.settings -> backend.modules.settings.http`): no spike was run; `test_every_contract_bites` is parametrised over the TOML and proves it in T402 step 4.
- `import.meta.glob` under vitest 5 and under dependency-cruiser's parser: T403 step 4. Fallback if either fails: an explicit list `src/modules/messages.js` with one import per module and language.
- A nested route with an absolute `path` and a `name` under the layout route in vue-router 4: T403 step 4 (`router.resolve('/settings')` matches two records).
- The leaf-key counts of `en.js` and `bg.js` (no Node in the planning shell): measured by the executor before and after each PR that moves texts.

## 5. Existing tests

All of `backend/tests/**` and `frontend/src/**/*.test.js` stay green without edits, except:

| File | Edit | Kind |
|------|------|------|
| `backend/tests/test_api_settings.py:184` | `logger='backend.routers.settings'` becomes `logger='backend.modules.settings.http'` | dotted path of the moved module |
| `backend/tests/architecture/test_sql_ownership.py:42-43` | `'routers/settings.py'` becomes `'modules/settings/infrastructure/repository.py'` (two places) | file path of the moved SQL |
| `backend/tests/architecture/test_ratchet.py`, `test_sql_ownership.py` | the two `growth_verdict(...)` calls pass `approved=` (T401) | deliberate, reviewed edit of the ratchet (step 0 plan, section 4) |
| `backend/tests/architecture/module_map.py` | one new key for `modules/registry.py` (T402) | data of the T304 test |
| the 7 frontend test files that move in T404 | relative import and `vi.mock` paths only | import path |

`backend/tests/conftest.py` is not edited: `from backend.routers import settings as settings_router` resolves to the alias.

## 6. Open to the owner and hand-offs

1. **Net allowlist change of step 1 is +1 line** (3 deleted, 4 added). The added lines are debt that already exists and becomes visible: settings calls `fire.repository.resolve_hq_alerts` and `fire.service.notify_alerts_updated` inside its request (until the `HQCleared` event of step 4), settings tells fire to re-evaluate (until the outbox of step 4; before, `main.py` did the wiring, so no import existed), and the alias file (until step 5). Accept, or move the `HQCleared` reaction earlier.
2. **`fire.api` does not exist yet.** The spec says settings calls `fire.api.request_evaluation`; until step 2 creates `backend/modules/fire/api.py` the publisher calls `backend.fire.service.service.request_evaluation`. Step 2 repoints the three lines (renamed lines need an approval entry again).
3. **`useSettings.js` is not about settings.** It holds the BG Mountains online or offline tile choice and belongs to `maps` (step 5). This plan moves it into `settings` because the task list says so; the alternative is to leave it in `src/composables/` until step 5 and save one move. T404 keeps it in its own commit so it can be dropped.
4. **The Settings page embeds other modules:** fire zones (`SuppressionZoneForm`, `stores/fire`), test mode (`TestModeCard`, simulation) and offline maps (`OfflineMapsCard`, maps), and their strings live in the `settings.*` namespace. They stay as they are. Step 2 has to decide how fire contributes its section (a `panels` contribution to the settings page) before `stores/fire` becomes module-internal.
5. **Where `get_current_user` and `require_role` end up** (`backend/auth.py` until step 5): every module's `http.py` imports them; no contract covers that edge today and `ALLOWED_EDGES` has no `<module> -> identity`. Proposal for step 5: they move to `backend/core/auth.py`.
6. **To the architecture owner (text proposals, not edited here):** modular-monolith.md 3.1 (anatomy table of section 1.1, `tasks.py` optional), 3.2 (frontend manifest: `order` on navigation items, named routes), 8 (the approval file as the fourth allowlist place; the frontend ratchet is count-based and has no approval path), 9 (step 1 done criteria).
7. **CI:** the growth tests still skip on PRs without full history (`fetch-depth: 0`, step 0 plan item 3, owner's workflow file).
8. `README.md` file tree (owner-written) does not show `backend/modules/` or `frontend/src/modules/`.

---

### Task 400: module loader in the kernel, `main.py` reads the list, smoke covers `/api/settings`

**risk:** security
**owner:** implementer
**Files:**
- Modify: `backend/core/modules.py` (three new functions, existing code untouched)
- Modify: `backend/main.py` (import of `MODULES` and of the loader functions; one call after `app.include_router(settings_router.router)`; start and stop of module tasks inside `lifespan`)
- Modify: `tools/smoke.py` (new method `s_settings` and one `self.step(...)` line), `docs/SMOKE.md` (one table row)
- Create: `backend/tests/modules/core/test_module_loader.py`
- Modify: `backend/tests/test_smoke_script.py` (two new tests appended)

**Interfaces:**
- Consumes: `backend.core.modules.{ModuleManifest, validate_manifest}`, `backend.modules.MODULES` (empty tuple today).
- Produces in `backend/core/modules.py`:
  - `check_modules(modules: Iterable[ModuleManifest]) -> list[str]`: every problem of `validate_manifest` for each manifest plus `'module <name> is listed twice'`; empty list means valid.
  - `include_module_routers(app: FastAPI, modules: Iterable[ModuleManifest]) -> None`: raises `ValueError('invalid module list: ' + '; '.join(problems))` before mounting anything when `check_modules` is not empty; otherwise `app.include_router(m.router)` in list order for every manifest whose `router` is not `None`.
  - `start_module_tasks(modules: Iterable[ModuleManifest], on_done: Callable[[asyncio.Task, str], None]) -> list[asyncio.Task]`: one `asyncio.create_task(fn())` per entry of `m.tasks`, task name `'<module>.<function name>'`, and a done-callback bound with `functools.partial` that calls `on_done(task, name)` (a `lambda` written in the loop would give every task the last name).
  - `async stop_module_tasks(tasks: Iterable[asyncio.Task]) -> None`: cancels all, then awaits them with `asyncio.gather(*tasks, return_exceptions=True)`.
- Produces in `main.py`: `include_module_routers(app, MODULES)` on the line after `app.include_router(settings_router.router)`; in `lifespan`, `module_tasks = start_module_tasks(MODULES, _log_task_failure)` after `alarm_task` is created and `await stop_module_tasks(module_tasks)` before `await close_pool()`. `_log_task_failure(task, name)` already has the right signature.
- Produces in `tools/smoke.py`: step `'g. GET /api/settings = 200'`, `needs=('c. admin login + token refresh',)`, placed after step e; `s_settings` requests `GET /api/settings` with the token, expects 200 and a JSON object containing the key `hq_radius_m`, returns `'settings row readable'`.

- [ ] **Step 1: Write the failing tests**, tagged `T400`. In `test_module_loader.py`:
  `test_include_module_routers_mounts_in_list_order` (two manifests `alpha` and `beta` with routers serving `/a` and `/b`; after the call the paths of `app.routes` end with `['/a', '/b']`);
  `test_a_manifest_without_router_is_skipped` (`ModuleManifest(name='gamma')` adds no route and raises nothing);
  `test_include_module_routers_refuses_an_invalid_list` (parametrised: a manifest named `'Bad'`, and two manifests named `'alpha'`; `pytest.raises(ValueError, match='invalid module list')`, and `app.routes` is the same list as before the call);
  `test_start_and_stop_module_tasks` (manifest `alpha` with the tasks `boom` (raises `RuntimeError('x')`) first and `ok` (awaits an `asyncio.Event` forever) second; after `await asyncio.wait([boom_task])` and one more `await asyncio.sleep(0)`, `on_done` was called exactly once, with the boom task and the name `'alpha.boom'`; after `await stop_module_tasks(tasks)` every task is done, `ok` is cancelled and `on_done` was also called with the name `'alpha.ok'`);
  `test_main_uses_the_loader` (parse `backend/main.py` with `ast`: there is a call `include_module_routers(app, MODULES)` at module level, and inside `lifespan` the calls `start_module_tasks` and `stop_module_tasks`, the latter on an earlier line than `close_pool()`);
  `test_every_module_router_is_mounted_in_the_real_app` (for every manifest in `backend.modules.MODULES` with a router, each pair `(route.path, frozenset(route.methods))` of the router appears exactly once in `backend.main.app.routes`; true for an empty list too).
  In `test_smoke_script.py`: `test_settings_step_passes_on_200_with_a_settings_row` and `test_settings_step_fails_on_503` (the HTTP helper is replaced the same way the existing step tests of that file replace it; the second expects a `FAIL` line whose text contains `GET /api/settings`).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\core\test_module_loader.py -q`. Expected: FAIL with `ImportError: cannot import name 'include_module_routers'`.
- [ ] **Step 3: Implement** the four functions (they import nothing from `backend.modules`: the kernel imports no module), the three `main.py` edits and the smoke step. No other line of `main.py` changes.
- [ ] **Step 4: Run** the new tests and the suites that import `main`. Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\core backend\tests\architecture backend\tests\test_smoke_script.py backend\tests\test_startup_migrations.py backend\tests\test_simulation.py backend\tests\test_b49.py backend\tests\test_b51.py backend\tests\test_api_fire_alerts.py backend\tests\test_fire_anonymise.py backend\tests\test_migrate_backup_guard.py -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(core): T400 mount module routers and tasks from the module list`.

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\core backend\tests\architecture backend\tests\test_smoke_script.py backend\tests\test_startup_migrations.py backend\tests\test_simulation.py backend\tests\test_b49.py backend\tests\test_b51.py backend\tests\test_api_fire_alerts.py backend\tests\test_fire_anonymise.py backend\tests\test_migrate_backup_guard.py -q`

### Task 401: architecture guards for the first module (approvals, manifest wiring, boundary coverage)

**risk:** normal
**owner:** implementer
**Files:**
- Create: `backend/tests/architecture/approved_additions.py`
- Modify: `backend/tests/architecture/test_ratchet.py` (`growth_verdict` gets `approved`; `test_allowlist_never_grows` passes it; new tests appended)
- Modify: `backend/tests/architecture/test_sql_ownership.py` (`test_sql_allowlist_never_grows` passes `approved`)
- Modify: `backend/tests/architecture/rules.py` (two new functions and one constant), `backend/tests/architecture/test_manifest.py` (new tests appended; `test_real_module_list_is_complete` also asserts the two new checks return `[]`)
- Modify: `backend/tests/architecture/importlinter.toml` (`"backend.modules"` appended to `source_modules` of the contracts `shims` and `fire-private`; no `ignore_imports` line changes)

**Interfaces:**
- Consumes: `test_ratchet.{entries, growth_verdict}`, `rules.check_module_list`, `backend.core.ws.FORWARDED_CHANNELS`.
- Produces in `approved_additions.py`: `APPROVED: dict[str, dict[str, str]]` keyed by the repo-relative allowlist file (`'backend/tests/architecture/importlinter.toml'`, `'backend/tests/architecture/allowlist.json'`); each value maps an entry exactly as `test_ratchet.entries()` prints it (`'<contract name>: <a> -> <b>'`) to the reason. Both dictionaries are empty after this task.
- Produces: `growth_verdict(rel: str, kind: str, cwd: Path, approved: Collection[str] = ()) -> tuple[str, str]`: entries in `approved` are not counted as growth; everything else as before.
- Produces in `rules.py`:
  - `LEGACY_SOURCES = ('backend.routers', 'backend.fire', 'backend.hardware_reader', 'backend.simulation', 'backend.main', 'backend.auth', 'backend.db')`.
  - `check_boundary_contracts(toml_text: str, module_names: Iterable[str], backend: Path) -> list[str]`: for each name the contract `module boundary: <name>` has `type == 'forbidden'`; its `forbidden_modules` equal the set `backend.modules.<name>.<child>` for every child that is a `.py` file or a folder with an `__init__.py`, other than `api` and `__init__` (so `__pycache__` is not a child); its `source_modules` contain every entry of `LEGACY_SOURCES` and `backend.modules.<other>` for every other name.
  - `check_manifest_wiring(manifests: Iterable[ModuleManifest], backend: Path) -> list[str]`: when `modules/<name>/http.py` exists, `manifest.router` is the `router` object of `backend.modules.<name>.http`, and without that file it is `None`; every `live_messages` entry is in `FORWARDED_CHANNELS`; every task is a coroutine function whose `__module__` is `backend.modules.<name>.tasks`.

- [ ] **Step 1: Write the failing tests**, tagged `T401`. In `test_ratchet.py` (using the existing `repo` and `ci_off` fixtures): `test_an_approved_addition_passes_and_an_unapproved_one_fails` (base has line `a -> b`; head adds `c -> d`; verdict `fail` without approval, `ok` with `approved={'x: c -> d'}` for a contract named `x`); `test_every_approval_is_still_in_its_file` (for both real files, every key of `APPROVED[rel]` is in `entries(<file text>, kind)`; the failure message says `delete this approval`); `test_approvals_have_a_reason` (every value has at least 20 characters). In `test_manifest.py`: `test_boundary_contract_rules_bite_on_a_tmp_tree` (a tmp tree with modules `a` and `b`, each with `api.py`, `http.py`, `domain/`; a complete TOML gives `[]`; removing `backend.modules.b` from the sources of `a`, removing `backend.modules.a.http` from the forbidden list, and adding `backend.modules.a.api` to it each give one problem naming the contract); `test_manifest_wiring_rules_bite` (fixture manifests: a router that is not the `http` router, a live message `'nope'`, a plain function as task: one problem each); `test_shims_and_fire_private_contracts_cover_modules` (both contracts list `backend.modules` in `source_modules`).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\architecture -q --task T401`. Expected: FAIL with `ModuleNotFoundError: No module named 'backend.tests.architecture.approved_additions'`.
- [ ] **Step 3: Implement** the interfaces above and the two TOML edits. `backend/modules/` holds no module yet, so `test_real_code_satisfies_all_contracts` stays green with the wider sources.
- [ ] **Step 4: Run** the whole directory (the T304 and T305 tests run against the changed helpers). Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\architecture -q`. Expected: PASS.
- [ ] **Step 5: Commit** `test(architecture): T401 approved allowlist additions and module wiring checks`.

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\architecture -q`

### Task 402: backend `settings` module

**risk:** security
**owner:** implementer
**Files:**
- Create: `backend/modules/settings/__init__.py` (docstring), `module.py`, `api.py`, `http.py`, `domain/__init__.py`, `domain/models.py`, `infrastructure/__init__.py`, `infrastructure/repository.py`, `infrastructure/publisher.py`
- Modify: `backend/routers/settings.py` (becomes the alias of section 1.3 with `<name>` = `settings`, `<file>` = `http`)
- Create: `backend/modules/registry.py` (`from .settings.module import manifest as settings_manifest` and `MODULES: tuple[ModuleManifest, ...] = (settings_manifest,)`)
- Modify: `backend/modules/__init__.py` (the eager `MODULES = ()` is replaced by a module-level `__getattr__(name)` that returns `registry.MODULES` for `'MODULES'` and raises `AttributeError` for any other name; the file imports nothing at import time)
- Modify: `backend/tests/architecture/module_map.py` (new key `'modules/registry.py': ('core',)`)
- Modify: `backend/main.py` (delete line 20 `from .routers import settings as settings_router`, line 181 `settings_router.after_change = fire_alarm.request_evaluation`, line 265 `app.include_router(settings_router.router)`)
- Modify: `backend/tests/architecture/importlinter.toml`, `approved_additions.py`, `allowlist.json` (`completed_step`: 1)
- Modify: `backend/tests/architecture/test_sql_ownership.py:42-43` (path string), `backend/tests/test_api_settings.py:184` (logger name)
- Create: `backend/tests/modules/settings/__init__.py`, `backend/tests/modules/settings/test_settings_module.py`

**Interfaces:**
- Consumes: `include_module_routers` and the `MODULES` loop in `main.py` (T400); `APPROVED`, `check_boundary_contracts`, `check_manifest_wiring` (T401); `backend.auth.{get_current_user, require_role}`, `backend.core.database.get_conn`, `backend.fire.repository.resolve_hq_alerts`, `backend.fire.service.{notify_alerts_updated, service}`.
- Produces:
  - `domain/models.py`: `StrictLat`, `StrictLon`, `StrictInt`, `HQIn`, `HQPatch`, `SettingsIn`, `SettingsUpdate`, `SettingsOut`, copied unchanged from `routers/settings.py:22-68` (pydantic only).
  - `infrastructure/repository.py`: `async fetch_settings(conn) -> asyncpg.Record | None`, `async row_exists(conn) -> bool`, `async update_settings(conn, body: SettingsUpdate, user_id) -> asyncpg.Record | None`, `async update_hq(conn, latitude, longitude, user_id) -> asyncpg.Record | None`, `async set_initial_hq(conn, latitude, longitude, user_id) -> asyncpg.Record | None`. The five SQL strings, their parameter order and the connection method per statement (`fetchrow` for the SELECT and the three UPDATEs, `fetchval` for the existence check) are copied unchanged: the existing tests read `mock_conn.fetchrow.call_args`.
  - `api.py`: `@dataclass(frozen=True) class SettingsChanged` with no fields (the settings table has one row; an event carries IDs only, DP-02).
  - `infrastructure/publisher.py`: `publish(event: SettingsChanged) -> None`: calls `fire_service.service.request_evaluation()` (looked up at call time through `from ....fire import service as fire_service`); any exception is caught and logged with `logger.error('settings: could not deliver %s: %s', type(event).__name__, exc)`.
  - `http.py`: `router = APIRouter(prefix='/api/settings', tags=['settings'])`; module attributes `logger`, `Conn`, `fire_repository` (`from ...fire import repository as fire_repository`), `notify_alerts_updated` (`from ...fire.service import notify_alerts_updated`) and `after_change: Callable[[], None] | None`, whose default is the module function `_publish_settings_changed()` (it calls `publisher.publish(SettingsChanged())`); the four endpoint functions keep their names (`get_settings`, `put_settings`, `put_hq`, `put_hq_initial`), response models, status codes, detail strings, log lines and the order of work inside each request: `put_settings` and `put_hq` run the UPDATE and, when HQ is cleared, `fire_repository.resolve_hq_alerts` in one `conn.transaction()`, then `notify_alerts_updated`, then the log line, then `after_change`; `put_hq_initial` has no transaction, no resolve and no notify (UPDATE, log line, `after_change`); `get_settings` only reads.
  - `module.py`: `manifest = ModuleManifest(name='settings', owns_tables=('settings',), router=http.router)`.
  - `importlinter.toml`: the three stale lines are gone (`backend.routers.settings -> backend.database`, `-> backend.fire.repository`, `-> backend.fire.service`); new lines in `fire-private`: `backend.modules.settings.http -> backend.fire.repository`, `backend.modules.settings.http -> backend.fire.service`, `backend.modules.settings.infrastructure.publisher -> backend.fire.service`, each `# until step 4`; new contract with `id = "boundary-settings"`, `name = "module boundary: settings"`, `type = "forbidden"`, `source_modules` = `rules.LEGACY_SOURCES`, `forbidden_modules = ["backend.modules.settings.domain", "backend.modules.settings.http", "backend.modules.settings.infrastructure", "backend.modules.settings.module"]`, `allow_indirect_imports = true`, and an `ignore_imports` list with the one entry `"backend.routers.settings -> backend.modules.settings.http",  # until step 5`, written in the multi-line form of the other contracts (one entry per line, the closing bracket on its own line: a comment on the bracket's line would swallow it). The four new lines are entered in `APPROVED` with the reasons of section 6 item 1; the PR body lists them, because an approval added in the same PR as its line is guarded by review only.

- [ ] **Step 1: Write the failing tests** in `test_settings_module.py`, tagged `T402`, using the `client`, `mock_conn` and `admin_user` fixtures of `conftest.py` and `ROW` copied from `test_api_settings.py`:
  `test_old_router_path_is_the_module_http` (`import backend.routers.settings as old, backend.modules.settings.http as new`; `old is new`; `from backend.routers import settings as via_pkg`; `via_pkg is new`);
  `test_importing_the_old_path_first_works` (subprocess `[sys.executable, '-c', 'import backend.routers.settings as s; print(s.__name__)']` with `cwd=REPO` prints `backend.modules.settings.http` and exits 0);
  `test_manifest` (`manifest.name == 'settings'`, `owns_tables == ('settings',)`, `depends_on == ()`, `tasks == ()`, `live_messages == ()`, `manifest.router is http.router`, `manifest in backend.modules.MODULES`, and `backend.modules.settings` is still the package: `import backend.modules.settings.http as h` works after `from backend.modules import MODULES`);
  `test_importing_the_api_does_not_import_http` (subprocess `[sys.executable, '-c', "import sys, backend.modules.settings.api; print('backend.modules.settings.http' in sys.modules, 'backend.fire.service' in sys.modules)"]` with `cwd=REPO` prints `False False`);
  `test_main_no_longer_wires_settings` (the text of `backend/main.py` contains neither `settings_router` nor `after_change`);
  `test_settings_routes_are_served_once_by_the_real_app` (`backend.main.app.routes` holds exactly one route for each of `('/api/settings', {'GET'})`, `('/api/settings', {'PUT'})`, `('/api/settings/hq', {'PUT'})`, `('/api/settings/hq-initial', {'PUT'})`);
  `test_settings_routes_keep_their_place` (in `backend.main.app.routes` the first `/api/settings` route comes after the last route whose path starts with `/api/fire` and before the `/ws` route);
  `test_openapi_operation_ids_are_unchanged` (`app.openapi()['paths']` has `get_settings_api_settings_get`, `put_settings_api_settings_put`, `put_hq_api_settings_hq_put`, `put_hq_initial_api_settings_hq_initial_put`, and the 200 response of each references `SettingsOut`);
  `test_a_saved_change_asks_fire_to_re_evaluate` (no patch of `after_change`; `monkeypatch.setattr(backend.fire.service.service, 'request_evaluation', lambda: calls.append(1))`; `mock_conn.fetchrow` returns `ROW` with HQ set; `PUT /api/settings/hq` with a position answers 200 and `calls == [1]`; the same for `PUT /api/settings` and `PUT /api/settings/hq-initial`);
  `test_fire_is_asked_after_the_transaction_and_the_broadcast` (one list `order` records: `tx.__aexit__` of the mocked transaction appends `'commit'`, a patched `notify_alerts_updated` appends `'notify'`, a patched `request_evaluation` appends `'evaluate'`; `PUT /api/settings/hq` clearing HQ gives `['commit', 'notify', 'evaluate']`, so fire never re-evaluates against settings that are not committed yet);
  `test_publish_failure_does_not_fail_the_request` (`request_evaluation` patched to raise `RuntimeError('boom')`; `PUT /api/settings/hq` answers 200; `caplog` at ERROR for `backend.modules.settings.infrastructure.publisher` has one record containing `SettingsChanged`);
  `test_a_refused_change_publishes_nothing` (`mock_conn.fetchrow` returns `None` and `fetchval` returns `1`: `PUT /api/settings` answers 409 `settings_stale` and `calls == []`; a body with `hq_radius_m: 99` answers 422 and `calls == []`);
  `test_domain_models_do_not_import_the_web_or_the_database` (parse `domain/models.py` with `ast`: imported top-level names are a subset of `{'datetime', 'typing', 'pydantic'}`).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\settings -q`. Expected: FAIL with `ModuleNotFoundError: No module named 'backend.modules.settings'`.
- [ ] **Step 3: Move.** `git mv backend/routers/settings.py backend/modules/settings/http.py`; split models and SQL out of it into `domain/models.py` and `infrastructure/repository.py`; add `api.py`, `publisher.py`, `module.py`; repoint its imports (`...auth`, `...core.database`, `...fire`); write the alias at the old path; write `registry.py` and the lazy `__init__.py`; add the `module_map` key; delete the three `main.py` lines; apply the two path-string test edits of section 5.
- [ ] **Step 4: Shrink and extend the allowlist.** Run `.venv\Scripts\python backend\tests\architecture\regen.py --remove-stale` (deletes the three stale lines), add the three `fire-private` lines, the boundary contract and the four `APPROVED` entries, set `completed_step` to 1. Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\architecture -q`. Expected: PASS, including `test_every_contract_bites[module boundary: settings]` and, non-vacuous for the first time, `domain is pure`, `test_no_sql_outside_infrastructure_in_the_real_modules`, `check_boundary_contracts` and `check_manifest_wiring`.
- [ ] **Step 5: Run** the module, the unedited API tests and the suites that import `main`. Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\settings backend\tests\test_api_settings.py backend\tests\architecture backend\tests\modules\core backend\tests\test_startup_migrations.py backend\tests\test_simulation.py backend\tests\test_fire_poller.py backend\tests\test_b49.py backend\tests\test_b51.py backend\tests\test_api_fire_alerts.py backend\tests\test_fire_anonymise.py backend\tests\test_migrate_backup_guard.py -q`. Expected: PASS.
- [ ] **Step 6: Commit** `refactor(settings): T402 settings becomes the first backend module`. PR body: the logger name change, the allowlist arithmetic (3 deleted, 4 added, reasons), the alias left behind.

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\settings backend\tests\test_api_settings.py backend\tests\architecture backend\tests\modules\core backend\tests\test_startup_migrations.py backend\tests\test_simulation.py backend\tests\test_fire_poller.py backend\tests\test_b49.py backend\tests\test_b51.py backend\tests\test_api_fire_alerts.py backend\tests\test_fire_anonymise.py backend\tests\test_migrate_backup_guard.py -q`

### Task 403: frontend module assembly (module list, routes, navigation, i18n merge)

**risk:** security
**owner:** implementer
**Files:**
- Create: `frontend/src/modules/index.js`, `frontend/src/platform/registry.js`
- Modify: `frontend/src/router/index.js` (the children array), `frontend/src/nav-config.js`, `frontend/src/i18n/en.js`, `frontend/src/i18n/bg.js` (first and last lines only), `frontend/.dependency-cruiser.cjs` (rule `lib-is-pure`)
- Create: `frontend/src/platform/registry.test.js`, `frontend/src/modules/modules.test.js`, `frontend/src/router/moduleRoutes.test.js`

**Interfaces:**
- Consumes: `validateManifest` from `src/platform/manifest.js` (not edited).
- Produces in `src/modules/index.js`: `export const MODULES = []` (one manifest per line, alphabetical; the comment says so).
- Produces in `src/platform/registry.js` (pure, imports only `./manifest.js`):
  - `checkModules(modules) -> string[]`: `validateManifest` problems prefixed with the module name; duplicate module names; duplicate route `name` or `path` across modules; duplicate navigation `to`; a navigation item whose `order` is not a finite number.
  - `collectRoutes(modules) -> object[]`: all `routes` in list order.
  - `collectNav(staticItems, modules) -> object[]`: static and module items sorted by `order`, stable.
  - `mergeMessages(core, dictionaries) -> object`: deep merge of plain objects, `core` first, then `dictionaries` in the given order; never throws; when a leaf is defined twice the first value stays.
  - `messageCollisions(core, dictionaries) -> string[]`: dotted keys defined by more than one source.
  - `leafKeys(dictionary) -> string[]`: dotted keys of all leaves, sorted.
- Produces in `router/index.js`: the layout route's `children` are the eight static children followed by `...collectRoutes(MODULES)`; `guard` is unchanged.
- Produces in `nav-config.js`: the static items carry `order` 10 (`/map`), 20 (`/users`), 30 (`/groups`), 40 (`/devices`), 50 (`/export`), 60 (`/selectofflinemap`), 70 (`/settings`), 80 (`/about`); `export const NAV_ITEMS = collectNav(STATIC_NAV, MODULES)`.
- Produces in `i18n/en.js` and `bg.js`: the literal becomes `const core = { ... }` and the default export is `mergeMessages(core, Object.values(import.meta.glob('../modules/*/i18n/en.js', { eager: true, import: 'default' })))` (`bg.js` globs `bg.js`). `i18n/index.js` is unchanged.
- Produces in `.dependency-cruiser.cjs`: `lib-is-pure` has `from: { path: '^src/(lib|modules/[^/]+/lib)/' }` and its `to.path` list gains `'^src/modules/[^/]+/(store\\.js$|views/|components/)'`. The rule name is unchanged.

- [ ] **Step 1: Measure and write the failing tests.** On the unchanged tree run `cd bee-with-me\frontend; node --input-type=module -e "import en from './src/i18n/en.js'; import bg from './src/i18n/bg.js'; const n=(o)=>Object.values(o).reduce((s,v)=>s+(v&&typeof v==='object'?n(v):1),0); console.log(n(en), n(bg))"` and keep both numbers for step 4 and the PR body (they are not written into a test: an unrelated PR that adds a text must not break this suite). Tests, each `[T403]`:
  in `registry.test.js`: `collectRoutes keeps list order`; `collectNav sorts static and module items by order` (static 10 and 30, module 20, result 10, 20, 30); `checkModules names an invalid manifest, a duplicate name, a duplicate route path, a duplicate nav target and a nav item without order`; `mergeMessages merges nested namespaces and keeps the first value on a collision without throwing` (`core = { nav: { map: 'Map' } }`, module `{ nav: { settings: 'Settings', map: 'X' }, settings: { title: 'T' } }` gives `nav.map === 'Map'`, `nav.settings === 'Settings'`, `settings.title === 'T'`); `messageCollisions reports nav.map for that input`; `leafKeys lists dotted keys`;
  in `modules.test.js` (first line `// @vitest-environment node`): `the real module list is valid` (`checkModules(MODULES)` is `[]`); `every folder under src/modules with an index.js is in the list and the reverse` (compares `fs.readdirSync` with `MODULES.map(m => m.name)`); `each module's i18n is its own files and en and bg have the same keys` (for each manifest, `leafKeys(m.i18n.en)` equals `leafKeys(m.i18n.bg)`, and `m.i18n.en` is the default export of `src/modules/<name>/i18n/en.js`); `no key is defined twice` (`messageCollisions` over the core literal and the module dictionaries is `[]` for both languages; the core literal is reached through a named export `core` of `en.js` and `bg.js`); `the merged dictionaries are the core plus the module files` (`leafKeys(en)` equals the sorted union of `leafKeys(core)` and the leaf keys of every `src/modules/*/i18n/en.js`, the same for `bg`); `navigation order is unchanged` (`NAV_ITEMS.map(i => i.to)` equals `['/map', '/users', '/groups', '/devices', '/export', '/selectofflinemap', '/settings', '/about']`); `a file that re-exports from src/modules is only a re-export` (every `.js` file under `src/stores`, `src/composables`, `src/lib` whose text contains `export * from '../modules/` matches, after removing comment lines, `^export \* from '\.\./modules/[^']+'\s*$`; a file that imports from `../modules/` without re-exporting, as `useMap.js` will, is not a shim and is not checked); `mergeMessages does not change its inputs` (in `registry.test.js`: `core` and each dictionary deep-equal a copy taken before the call, so the collision test cannot be fooled by a mutated `core`); `module lib is pure` (a fixture tree under `os.tmpdir()` with `src/modules/m/lib/a.js` importing `../store.js` is cruised with the real rule set and yields `lib-is-pure|src/modules/m/lib/a.js|src/modules/m/store.js`; the cruise helper is copied from `architecture.test.js`, which is not edited);
  in `registry.test.js` also: `a module route is reachable under the layout and keeps its meta` (a router built like the real one from one fixture module route `{ path: '/x', name: 'x', component: {}, meta: { adminOnly: true } }`: `router.resolve('/x').matched.length === 2` and `router.resolve('/x').meta.adminOnly === true`); and in the new file `src/router/moduleRoutes.test.js` (default jsdom environment, because the real router needs `window`): `the real router serves every module route under the layout with its meta` (with `vi.mock('../api', ...)` as `router/index.test.js` does: for every route of `collectRoutes(MODULES)`, the real `router` of `src/router/index.js` resolves its `path` to a location with `matched.length === 2`, the same `name` and the same `meta.adminOnly`; this holds for an empty list and bites from T404 on); `the real router file spreads the module routes` (the text of `src/router/index.js` contains `...collectRoutes(MODULES)`).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/platform/registry.test.js src/modules/modules.test.js`. Expected: FAIL (`Failed to resolve import "./registry.js"`).
- [ ] **Step 3: Implement** the interfaces. `en.js` and `bg.js` also get `export { core }`.
- [ ] **Step 4: Run** the new tests, the architecture test and the suites that read the router, the navigation and the dictionaries. Run: `cd bee-with-me\frontend; npm test -- src/platform src/modules src/architecture.test.js src/router src/i18n src/components/AppLayout.test.js; npm run build`. Expected: PASS and a clean build. Run the one-liner of step 1 again: both numbers are unchanged. If `import.meta.glob` is rejected by vitest or by the cruiser, use the fallback of section 4 and say so in the PR body.
- [ ] **Step 5: Commit** `feat(platform): T403 assemble routes, navigation and i18n from the module list`.

dod:
- `cd bee-with-me\frontend; npm test -- src/platform src/modules src/architecture.test.js src/router src/i18n src/components/AppLayout.test.js`
- `cd bee-with-me\frontend; npm run build`

### Task 404: frontend `settings` module

**risk:** security
**owner:** frontend-designer
**Files:**
- Create: `frontend/src/modules/settings/index.js`, `frontend/src/modules/settings/i18n/en.js`, `frontend/src/modules/settings/i18n/bg.js`
- Move: `frontend/src/views/SettingsView.vue` and `SettingsView.test.js`, `SettingsView.b54.test.js`, `SettingsView.photo.test.js`, `SettingsView.zones.test.js` to `frontend/src/modules/settings/views/`
- Move: `frontend/src/stores/settings.js` to `frontend/src/modules/settings/store.js`, `stores/settings.test.js` to `modules/settings/store.test.js`
- Move: `frontend/src/lib/settingsForm.js` and `settingsForm.test.js` to `frontend/src/modules/settings/lib/`
- Move: `frontend/src/composables/useSettings.js` and `useSettings.test.js` to `frontend/src/modules/settings/composables/` (own commit, section 6 item 3)
- Create: `frontend/src/stores/settings.js`, `frontend/src/composables/useSettings.js` (re-exports of section 1.3)
- Modify: `frontend/src/modules/index.js` (one line), `frontend/src/router/index.js` (delete the `settings` child), `frontend/src/nav-config.js` (delete the `/settings` item), `frontend/src/i18n/en.js` and `bg.js` (delete the `settings` namespace and the `nav.settings` line), `frontend/src/architecture.allowlist.json` (`completed_step`: 1)
- Test: `frontend/src/modules/settings/index.test.js`

**Interfaces:**
- Consumes: `MODULES`, `collectRoutes`, `collectNav`, `mergeMessages` and the tests of T403.
- Produces in `modules/settings/index.js` (default export): `name: 'settings'`; `routes: [{ path: '/settings', name: 'settings', component: () => import('./views/SettingsView.vue'), meta: { adminOnly: true } }]`; `nav: [{ to: '/settings', labelKey: 'nav.settings', icon: '⚙', adminOnly: true, order: 70 }]`; `mapLayers: []`, `panels: []`, `banners: []`, `liveHandlers: {}`, `i18n: { en, bg }`, `depends: []`. The file imports only its two dictionaries (T427 of the map-shell plan later adds one import of a plain-data layer declaration; a manifest never imports OpenLayers).
- Produces in `modules/settings/i18n/en.js` and `bg.js`: `{ nav: { settings: ... }, settings: { ... } }` with the texts moved verbatim (including the `settings.*` keys used by `OfflineMapsCard.vue` and `TestModeCard.vue`).
- Unchanged public names: `useSettingsStore`, `isTransientFailure`, `useSettings`, `setBgMountainsOffline`, `resolveBgMountainsDefault`, and the helpers of `settingsForm.js`. `MapView.vue`, `useMap.js` and `OfflineMapsCard.vue` are not edited: they import through the two re-exports.

- [ ] **Step 1: Write the failing test** `modules/settings/index.test.js`: `it('the settings manifest is valid and admin-only [T404]')` (`validateManifest(manifest)` is `[]`; the route has `meta.adminOnly === true` and `name === 'settings'`; the nav item has `order === 70` and `adminOnly === true`); `it('the real router keeps /settings admin-only [T404]')` (with `vi.mock('../../api', () => ({ getMe: vi.fn(), login: vi.fn() }))`: `const to = router.resolve('/settings')` on the real router has `to.matched.length === 2`, `to.name === 'settings'`, `to.meta.adminOnly === true`; with a viewer in the auth store `await guard(to)` is `'/map'`, with an admin it is `undefined`); `it('old store and composable paths are the same objects [T404]')` (`(await import('../../stores/settings.js')).useSettingsStore === (await import('./store.js')).useSettingsStore`; the same for `useSettings`); `it('the settings texts are in the merged dictionaries [T404]')` (`en.settings.title` and `bg.settings.title` from `src/i18n/en.js` and `bg.js` are non-empty strings and differ; `en.nav.settings` is a non-empty string).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/modules/settings`. Expected: FAIL (`Failed to resolve import "./index.js"`).
- [ ] **Step 3: Check the mocks first.** Run `git grep -nE "vi\.mock\('[^']*(stores/settings|useSettings|settingsForm)" -- frontend/src`. Expected: no output (a mocked old path would not reach the moved file).
- [ ] **Step 4: Move** with `git mv`; in the moved files and tests change only relative paths, in imports and in `vi.mock(...)`: from `views/`, `lib/` and `composables/` (three levels below `src/`) `'../api'` becomes `'../../../api'`, `'../stores/x'` becomes `'../../../stores/x'`, `'../components/X.vue'` becomes `'../../../components/X.vue'`, `'../lib/fireErrors'` becomes `'../../../lib/fireErrors'`, and `'../i18n/index.js'`, `'../i18n/en.js'`, `'../i18n/bg.js'` become `'../../../i18n/...'` (the merged dictionaries); inside the module, `SettingsView.vue` imports `'../store'` and `'../lib/settingsForm'`; `store.js` (two levels below `src/`) imports `'../../api'`, `'../../api/client'`, `'../../stores/auth'` and `'./lib/settingsForm'`; `store.test.js` imports `'./store'` and `'../../stores/auth'` and mocks `'../../api'`; write the manifest, the two dictionaries and the two re-exports; add the `MODULES` line; delete the route, the nav item and the two i18n blocks; set `completed_step`. The component file keeps the name `SettingsView.vue`.
- [ ] **Step 5: Run** the module, the files that import through the re-exports, and the T403 invariants (collisions, parity, navigation order, shim purity). Run: `cd bee-with-me\frontend; npm test -- src/modules src/platform src/architecture.test.js src/router src/components src/views/MapView.test.js src/composables; npm run build`. Expected: PASS and a clean build with a `SettingsView` chunk. Run the leaf-count one-liner of T403 step 1 before and after the move: both numbers are unchanged; put them in the PR body.
- [ ] **Step 6: Commit** in two commits: `refactor(settings): T404 move the tile-source composable into the settings module` and `refactor(settings): T404 settings becomes the first frontend module`.

dod:
- `cd bee-with-me\frontend; npm test -- src/modules src/platform src/architecture.test.js src/router src/components src/views/MapView.test.js src/composables`
- `cd bee-with-me\frontend; npm run build`
