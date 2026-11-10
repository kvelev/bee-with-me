# Vertical slices, step 2: the `fire` module (backend and frontend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `fire` into a vertical-slice module on both sides (`backend/modules/fire/`, `frontend/src/modules/fire/`): the backend package and its router move behind `fire.api`, `main.py` stops naming fire, and every fire piece of the map (banner, layers, toggles, popup, context-menu item, dialogs, pill, zones section of the Settings page, live handlers) becomes a contribution of the fire manifest, with no change the operator can notice.

**Architecture:** The eight files of `backend/fire/` and `backend/routers/fire.py` move with `git mv` into the anatomy of modular-monolith.md 3.1; every old dotted path stays as a `sys.modules` alias, so the 24 test files that import or patch `backend.fire.*` and `backend.routers.fire` run unedited. Callers outside fire (`settings`, `routers/users.py`, `routers/devices.py`, `main.py`) reach fire only through `backend.modules.fire.api`; the reverse direction of those calls is debt until the outbox of step 4 and is carried as named, approved rows of a new ratchet (`module_edges`). On the frontend the legacy entries that wave 1 marked `// until step 2` move into the fire manifest and its map entry; two small contribution points are added first (panels with a host, a state hook on layer toggles), because fire needs them and `weather` and `sos` reuse them.

**Tech Stack:** Python 3.11+, FastAPI >= 0.142, asyncpg, pydantic, import-linter 2.x with grimp (existing dev dependency), pytest; Vue 3, Pinia, OpenLayers 10, vue-i18n 11, vitest, dependency-cruiser (existing). No new dependency.

**Spec:** [`docs/superpowers/specs/2026-10-31-vertical-slices-programme-design.md`](../specs/2026-10-31-vertical-slices-programme-design.md) sections 5 ("Step 2"), 6, 7, 9; `Architecture/application/modular-monolith.md` sections 3, 4, 7, 9; ADR 17, 18, 19; `Architecture/principles/architecture-principles.md` (binding). Template and lessons: [`2026-11-10-vs-step1-settings.md`](2026-11-10-vs-step1-settings.md) section 1, [`2026-11-10-vs-map-shell.md`](2026-11-10-vs-map-shell.md) section 1, [`2026-10-31-vs-phase0-1.bugs.md`](2026-10-31-vs-phase0-1.bugs.md) (B93 to B97).

**Base:** `upstream/develop` at `7f874bc` (PR #125, T460 merged). Plan branch: `docs/vs-wave2-plans`. Execution branches: `feature/vs-2-<task>` off `develop`, one PR per task. Wave overview: [`2026-11-10-vs-wave2-overview.md`](2026-11-10-vs-wave2-overview.md).

## Global Constraints

- Decisions that are not reopened: base branch `upstream/develop`; kernel `backend/core/` and `frontend/src/platform/`; `backend/main.py`, `backend/db/migrate.py`, `backend/version.py` do not move; old import paths stay thin re-exports until step 5 (backend: `sys.modules` alias, never `import *`; frontend: a file whose only statement is `export * from '<new path>'`); behaviour does not change; WebSocket security is not implemented; auth is the loader's default and an anonymous route is listed in `public_routes`; the shell contract of T422 and T423 (`shell.install(mapEntry, declarations, ctx)`, the `ctx` object) is not changed; `lib/groups.js` stays where it is; error isolation of contributions stays.
- `fire_alert`, `fire_alert_repeat`, `fire_alert_updated`, `fire_data_updated` and `fire_zones_updated` payloads are not touched (they keep `full_name` and `rank` until step 4).
- No schema change, no migration, no edit of `backend/hardware_reader/*`, `data/`, `tiles/`, `backend/uploads/`, `.env`. Owner-written files (`README.md`, `CHANGELOG.md`, `todo.md`, `docs/PROTOCOL.md`, `.github/workflows/**`, `deploy/**`, `package-lock.json`, `docker/docker-compose.yaml`) are not edited.
- Existing tests stay green and unedited except import paths, `vi.mock` paths and the edits listed in section 5. A task that needs any other edit of an existing test stops and reports.
- An allowlist line is deleted when it is stale and added only with an entry in `backend/tests/architecture/approved_additions.py` (reason of at least 20 characters); the PR body lists every deleted and added line.
- Tags: pytest `@pytest.mark.Trait("Task", "T5xx")` (double quotes; `B96` uses `Trait("Bug", "B96")`), vitest `it('... [T5xx]', ...)`. Commits: `type(scope): T5xx summary`, body ends with the Co-Authored-By line of the session.
- Frontend files `.vue` and `.css` are changed only by the `frontend-designer` agent. A frontend task keeps DOM structure, classes, `data-testid`, `data-layer`, texts, z-order, timers and keyboard behaviour; no new i18n key.
- Entry chunk: the base is **167,61 kB** (`npm run build` on `develop` at `7f874bc`, file `dist/assets/index-*.js`), not the 161 kB of the wave 1 plans. Every frontend PR states the number before and after. No `ol` module may enter the entry chunk (rule `manifest-reaches-no-openlayers`); growth from the fire store and the alarm banner is expected in T505 and is named in its PR body (section 6, item 2).
- Test runs follow the test-run policy: a task runs its own DoD; the full suites run once per PR in the PR gate (section 3).

## Review Focus

1. A `Mount` or a plain Starlette route in a module router is served without the auth dependency or is silently not served at all: the loader must refuse it before anything is mounted, unless it is declared public (T500, `test_a_mount_without_a_public_declaration_is_refused`).
2. The alarm actor stops being a named task of `main.py`: a tick that is running at shutdown must still finish its cancellation before the pool closes, and a crash of the poller or the alarm loop must still be logged by name (T503, `test_fire_tasks_are_stopped_before_the_pool_closes`, `test_a_crashed_fire_task_is_logged_by_name`).
3. A patch on the repository must still reach a caller that goes through `fire.api`: an api function that binds its implementation at import would make `monkeypatch.setattr(repository, 'resolve_disabled_alerts', fake)` test nothing (T503, `test_api_looks_the_implementation_up_at_call_time`).
4. Deleting a device permanently while the alarm tick runs: the lock timeout, the advisory lock and the resolve must stay on the request's connection, inside its transaction and in today's order, or an open alert is left without a device (T503, `test_device_delete_keeps_the_statement_order`).
5. A fire alarm must be on screen without waiting for a lazy chunk, and above nothing but SOS: the banner component is imported statically by the manifest and its priority is `BANNER_PRIORITY.fireAlarm` (T505, `the fire banner is a manifest contribution below SOS`).

---

## 1. What moves where

### 1.1 Backend

| Today | After | Old path |
|-------|-------|----------|
| `backend/fire/models.py`, `parse.py`, `proximity.py`, `h3index.py` | `backend/modules/fire/domain/` (same file names) | alias file per module in `backend/fire/` |
| `backend/fire/repository.py`, `sources.py`, `poller.py`, `service.py` | `backend/modules/fire/infrastructure/` (same file names) | alias file per module in `backend/fire/` |
| `backend/routers/fire.py` | `backend/modules/fire/http.py` | alias `backend/routers/fire.py` |
| the fire lines of `main.py` (router include, poller task, alarm task, `after_refresh` wiring) | `backend/modules/fire/module.py` and `tasks.py` | none |
| `main.py` retention loop (`_cleanup_old_locations`) | stays in `main.py`; its three fire functions come from `fire.api` | the names `main.anonymise_alerts`, `main.anonymise_hotspots`, `main.prune_fire_data` stay (four tests patch them) |

`service.py` and `poller.py` go to `infrastructure/` and not to `tasks.py`, because both run SQL on a connection (`pg_try_advisory_xact_lock`, `pg_notify`) and the rule "only `infrastructure/` runs SQL" (`sql_scan.scan_sql_outside_infrastructure`) would fail anywhere else; `tasks.py` holds two thin coroutines that start them. The request models of `routers/fire.py` (`DismissIn`, `FieldReportIn`, `ZoneIn`, `ZoneUpdate`, `ZoneVersion`, `AcknowledgeAllBody`) stay in `http.py`: the tests patch and read names on the router module, and the alias makes the old module the new one. `ALERT_OUT_SELECT` (SQL text in `models.py`) stays where it is; it is a string, not a connection call.

**Allowlist arithmetic on `7f874bc`** (the brief speaks of 14 lines; the count below is what the files hold):

| Lines today | Count | What happens | Task |
|-------------|-------|--------------|------|
| `shims`: `backend.fire.poller`, `backend.fire.service`, `backend.routers.fire` to `backend.database` (`# until step 2`) | 3 | deleted (the module imports `backend.core.database`) | T502 |
| `fire-private`: `backend.routers.fire` to `backend.fire.{models,parse,poller,repository,service}` (`# until step 2`) | 5 | deleted | T502 |
| `fire-private`: `backend.main` to `backend.fire.{poller,repository,service}` (`# until step 2`) | 3 | deleted (`main.py` imports `fire.api`, assembly code is exempt from the direction rule) | T503 |
| `fire-private`: `backend.modules.settings.http` (2), `settings.infrastructure.publisher` (1), `backend.routers.users` (2), `backend.routers.devices` (2) (`# until step 4`) | 7 | deleted as lines; carried as 4 rows of `module_edges` (one per importing file, target `backend.modules.fire.api`, `until: 4`), each with an approval; the 3 approvals of step 1 go with their lines | T503 |
| `allowlist.json`: `routers/devices.py`, `fire_alerts`, `UPDATE`, `until: 2` | 1 | deleted (the UPDATE moves into the fire repository) | T503 |
| new in `module boundary: fire`: 8 alias files of `backend/fire/` plus `backend.routers.fire` to their module (`# until step 5`) | +9 | added with approvals | T502 |

So 18 import lines and 1 SQL row go: 11 for good in step 2, 7 turn into 4 `module_edges` rows; 9 alias lines are new. The import allowlist goes from 45 lines to 46 after T502 and to 36 after T503; `sql_writes` from 21 rows to 20; `module_edges` from 0 to 4. `completed_step` becomes 2 in T503.

### 1.2 Frontend

| Piece today | After | Task |
|-------------|-------|------|
| `stores/fire.js` (+5 tests), `lib/fireErrors.js`, `lib/fireStyle.js` (+test each), `lib/fireTone.js`, `components/FireAlarmBanner.vue` (+test), namespaces `fire` and `fireAlarm` of `i18n/en.js` and `bg.js` | `modules/fire/{store.js, lib/, components/, i18n/}`; manifest `modules/fire/index.js` with the banner; re-exports at `stores/fire.js`, `lib/fireErrors.js`, `lib/fireStyle.js` | T505 |
| `composables/map/fireLayerList.js`, `fireLayers.js` (+test); the legacy install line in `useMap.js`; `FIRE_MAP_LAYERS` in `MapView.vue` | `modules/fire/map/layers.js`, `map/index.js`; manifest `mapLayers`; `modules/mapEntries.js` | T506 |
| `LEGACY_LAYER_NAMES`, `toggleFire`, `ensureLayer`, the fire pill, the attribution line, the zones note, the focus ring, the fire part of the first `onMounted`, the four fire watchers of `MapView.vue` | `modules/fire/components/FireMapPanel.vue` (a `map` panel) and the `toggle` state hook | T507 |
| legacy popup entry, popup actions, legacy context-menu item, the two dialogs, "Report fire at this position" of the tracker row | manifest `popups` and `contextMenu`; `modules/fire/components/{FireMapPopup,FireDialogs}.vue`, `modules/fire/ui.js`; `components/FirePopup.vue` and `FieldReportForm.vue` move | T508 |
| zones section of `modules/settings/views/SettingsView.vue`, `components/SuppressionZoneForm.vue` | `modules/fire/components/{FireZonesSettings,SuppressionZoneForm}.vue` (a `settings` panel) | T509 |
| the five fire lines and the two fire calls of `resync` in `composables/useWebSocket.js` | manifest `liveHandlers` and `live` | T510 |

**Timers.** `fireTimer` no longer exists under that name: the 60 s hotspot repaint lives in `composables/map/fireLayers.js` (`timer`, started in `shell.onMounted`, cleared in `dispose`) and moves with that file in T506; it is fire's. The 15 s clock of `FireAlarmBanner.vue` and the 2,5 s feedback timer of `FirePopup.vue` move with their components. `focusRingTimer` (8 s, `MapView.vue`) is fire's and moves in T507. `staleTimer` (`useMap.js`, 60 s restyle of the tracker markers) is **not** fire: it belongs to `tracking` and is handled in the tracking plan. `tickTimer` (10 s age labels) and `weatherTimer` stay with the tracker panel and the weather plan.

**Contract additions** (both optional, a manifest that is valid today stays valid):

- `panels` item: `{ id, component, host?, order? }` with `host` one of `PANEL_HOSTS = ['map-root', 'map', 'map-toolbar', 'settings']` and `order` a finite number (default 100). `collectPanels(modules, host, legacy = [])` returns the items of that host sorted by `order`, then `id`. `PanelHost.vue` renders them with one `context` prop and isolates a failing panel as `BannerStack.vue` does. Optional `retryKey: (context) => unknown` on a panel item: a panel that failed is rendered again when that value changes (without it a failed panel stays away until the host is mounted again).
- `mapLayers[].toggle`: optional `key` (text, rendered as `data-layer`), `isOn: () => boolean` and `set: (on: boolean) => void` (both or neither). A toggle without the pair is not rendered, as today.

A manifest may import components and its store statically where the piece must be on screen without a network round trip (alarm banner, live handlers) or where an unedited test mounts the host and expects the child at once (popup, panels). It never reaches OpenLayers (section 6, item 2), and that includes every component it imports: `modules.test.js:215` follows static imports through `.vue` files. The code that moves out of `MapView.vue` uses `Overlay`, `fromLonLat`, `toLonLat` and `unByKey` today; a moved component takes them from `context.mapKit`, which `MapView.vue` (a lazy route chunk that imports OpenLayers anyway) fills, and never writes `from 'ol...'` itself.

## 2. File map and who else touches each file (as of `7f874bc`)

Commands used: `git grep -nE "(from|import) +(backend|\.+)\.?fire\b|backend\.fire\.|from \.+fire" -- backend tools`; `git grep -nE "setattr\((devices|users|settings_router|fire_router|repository|repo|service_module|poller|main)[,.]|setattr\('backend\.(fire|routers|main)" -- backend/tests`; `git grep -nE "_cleanup_old_locations|fire_alarm|fire_poller|alarm_task|after_refresh" -- backend/tests`; `git grep -nE "from '[^']*(stores/fire|lib/fire|FirePopup|FireAlarmBanner|FieldReportForm|SuppressionZoneForm|fireLayerList|fireLayers|legacyBanners)" -- frontend/src`; `git grep -nE "vi\.mock\('[^']*(stores/fire|fire|composables/map)" -- frontend/src`; `git grep -nE "\.mount\(|StaticFiles|add_route\(|Mount\(" -- backend ":!backend/tests"`.

| File | This plan | Also read or written by |
|------|-----------|-------------------------|
| `backend/core/modules.py` | T500 | the loader of every module; `rules.py`, `test_module_loader.py`, `test_route_auth.py` |
| `backend/tests/architecture/rules.py`, `allowlist.json`, `approved_additions.py` (hot) | T500 (route check), T501 (`module_edges`), T502, T503 | weather plan T520, tracking plan T540 to T542 |
| `backend/tests/architecture/importlinter.toml` (hot) | T502, T503 | T520, T540 |
| `backend/main.py` (hot) | T502 (2 lines), T503 (fire imports, lifespan lines) | T520, T540 (one router each); tests `test_b93_lifespan_shutdown`, `test_fire_anonymise`, `test_fire_poller`, `test_b49`, `test_b51`, `test_simulation`, `test_startup_migrations`, `test_migrate_backup_guard`, `test_request_id`, `test_route_auth`, `test_module_loader`, `test_settings_module` import it |
| `backend/modules/registry.py` (hot) | T502 adds `fire` before `settings` | T520, T540 add one line each |
| `backend/fire/*.py` (8), `backend/routers/fire.py` | T502: become aliases | 24 test files import them (list in section 5); `backend/tests/conftest.py:17,31` |
| `backend/routers/users.py`, `backend/routers/devices.py` | T503: fire imports and the device-delete block | tracking plan T541 (their `location_events` / `sos_alerts` statements); tests `test_users_api.py:33-34`, `test_devices_api.py:76-77` patch `fire_repository` and `notify_alerts_updated` on them by dotted string |
| `backend/modules/settings/http.py`, `infrastructure/publisher.py` | T503: fire imports | `test_api_settings.py:280-299` patches `settings_router.fire_repository` and `notify_alerts_updated` |
| `tools/smoke.py`, `backend/tests/test_smoke_script.py`, `docs/SMOKE.md` | T502 adds step h | T520 (step i), T540 (step j) |
| `frontend/src/platform/manifest.js`, `platform/map-shell/contributions.js` | T504 | T543 of the tracking plan adds the `live` field to `manifest.js` |
| `frontend/src/views/MapView.vue` (hot, 1540 lines) | T504, T506, T507, T508 | overview T580; weather T522; tracking T545, T548; seven `MapView*.test.js` files mount it with `useMap` mocked |
| `frontend/src/composables/useMap.js` (hot, 873 lines) | T506 | overview T580; tracking T549; eight `useMap.*.test.js` files call the real composable |
| `frontend/src/modules/index.js`, `frontend/src/i18n/en.js`, `bg.js` (hot) | T505 | weather T521, tracking T544 |
| `frontend/src/modules/mapEntries.js` | T506 | tracking T549 |
| `frontend/src/components/legacyBanners.js`, `AppLayout.vue` | T505 deletes the fire line of the list | tracking T544 deletes the SOS line and the file |
| `frontend/src/composables/useWebSocket.js` (hot) | T510 | tracking T543 (creates the dispatch), T544 |
| `frontend/src/modules/settings/views/SettingsView.vue` (+4 tests) | T509 | none in this wave |

**Mounts (B96).** No module of wave 2 has a mount or a plain Starlette route: the only two are `app.mount('/uploads', ...)` and `app.mount('/tiles/bgmountains', ...)` in `main.py:283,286`; they belong to `people` (step 4) and `maps` (step 5). T500 is still the first task of the wave, so the guard exists before any later module can add one.

## 3. Task order, PRs, reviewers, parallel work

| PR | Task | Content | Needs | Owner | Reviewers |
|----|------|---------|-------|-------|-----------|
| 1 | T500 | B96: the loader refuses route types without dependencies | nothing | implementer | breaker + security-reviewer (`core/**`) |
| 2 | T501 | direction ratchet `module_edges` | nothing | implementer | breaker |
| 3 | T502 | backend fire module: move, aliases, loader mount | T500, T501 | implementer | breaker + security-reviewer (`routers/**`, `main.py`) |
| 4 | T503 | `fire.api`, callers, tasks from the manifest, `main.py` wiring | T502 | implementer | breaker + security-reviewer (`routers/**`, `main.py`) |
| 5 | T504 | panel contribution point and toggle state hook | overview T580 (map chain) | frontend-designer | breaker |
| 6 | T505 | frontend fire module, part 1 (store, libs, banner, texts) | nothing (assembly chain, section 3 of the overview) | frontend-designer | breaker |
| 7 | T506 | fire map entry and layer declarations | T505, T504 | frontend-designer | breaker |
| 8 | T507 | fire layer state, pill, attribution, focus ring | T506 | frontend-designer | breaker |
| 9 | T508 | popup, context-menu item, dialogs | T507 | frontend-designer | breaker |
| 10 | T509 | zones section of the Settings page | T508 | frontend-designer | breaker |
| 11 | T510 | fire live handlers | T505, tracking T543 | implementer | breaker |

**Inside the plan.** Backend (T500 to T503) and frontend (T504 to T510) share no file and run at the same time. T500 and T501 are parallel; T502 and T503 are a chain. T504, T506, T507, T508 are links of the wave's one map chain (`MapView.vue` and `useMap.js`: one session at a time, order in the overview). T505 touches the frontend assembly files and is ordered against T521 and T544 there. T509 edits `SettingsView.vue` only and T510 `useWebSocket.js` only.

**PR gate (every PR), in this order:** (1) the task's DoD; (2) `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests -q` when a backend file changed, `cd bee-with-me\frontend; npm test; npm run build` when a frontend file changed, with the entry chunk size before and after in the PR body; (3) `python tools/smoke.py` (see `docs/SMOKE.md`), PASS lines pasted into the PR body; from T502 on that includes step h; (4) for T504 to T509 a manual look at the moved element in the dev stack by the maintainer, as a checkbox in the PR body, and a reminder to run the impeccable detector; (5) `breaker` and, where the table says so, `security-reviewer` on the head commit until both end with `VERDICT: PASS`; (6) `gh pr create` is run by the human with `--body-file`. No `ef-migration-reviewer` (no migration) and no hardware validation (no file under `hardware_reader/` changes).

## 4. Risks, rollback, not verified

| Risk | Mitigation |
|------|------------|
| An alias makes two module objects for one file (state such as `poller.FEEDS` or `service.service` doubled) | the alias replaces `sys.modules[__name__]`, so the old name is the new module; `test_old_paths_are_the_new_modules` asserts identity for all nine and `test_importing_an_old_path_first_works` runs in a fresh interpreter |
| Logger names change (`backend.fire.poller` becomes `backend.modules.fire.infrastructure.poller`, and so on for nine loggers) | one test string edited (section 5); a log filter or a dashboard that matches the old names is not known in the repo; stated in the PR body |
| Shutdown: an exception of the alarm task after its cancellation is no longer raised out of `lifespan` | it is gathered by `stop_module_tasks` and logged by `_log_task_failure` with the task name `fire.alarm_loop`; the pool is closed; the B93 test is rewritten to pin exactly that (section 5) |
| The route table order changes: the fire routes stay in place (the module list is mounted where `fire.router` was), nothing else moves | `test_fire_routes_keep_their_place` |
| `resolve_disabled_alerts`, `resolve_hq_alerts` run inside the caller's transaction; a wrapper that opened its own would change atomicity | the api functions take the caller's `conn` and pass every argument through unchanged |
| The entry chunk grows by the fire store, the banner and the tone | measured and named in T505; no `ol`; the alternative (a second entry file per module) is section 6, item 2 |
| A panel rendered through `PanelHost` lands at another place of the DOM and a stacking order changes | the hosts sit where the moved blocks are today; the manual check of the PR gate covers it |
| A watcher replaces a direct call (`setFireLayerVisible` after a toggle) and a test reads the call in the same tick | the watchers of `FireMapPanel.vue` use `flush: 'sync'` |
| bee-dev gets a broken image | smoke gate before every PR; a bad merge is undone with `git revert -m 1 <merge>` |

**Rollback.** No schema or data change: `git revert -m 1 <merge commit>`, newest first inside a chain (T503, T502; T510; T509, T508, T507, T506, T505, T504). T500 and T501 stay (guards only). Backend and frontend revert independently.

**Not verified while planning (the executor checks it in the named step):**
- Checked while the plan was reviewed (FastAPI 0.142.2), so not left to the executor: `rules._ignore_import_problems` accepts an `ignore_imports` target only when it is a direct private child, so eight of the nine alias edges would be refused; T502 widens the rule to files below a private child and tests it. A `Mount` inside a nested `include_router` hides behind one `_IncludedRouter` and is neither refused nor served (404); T500 walks `effective_candidates()` for that reason.
- That `grimp.build_graph('backend')` sees the lazy import inside `backend/modules/__init__.py` and the function-level imports of `hardware_reader`: T501 step 1.
- That `@vue/test-utils` name stubs reach a component rendered through `PanelHost` (as T421 found for `BannerStack`): T504 step 4.
- The exact queries of the seven `MapView*.test.js` and four `SettingsView*.test.js` files on the moved markup: the first step of T506 to T509 reads them.
- No browser was opened and no build was run while planning; the 167,61 kB figure is the maintainer's measurement.

## 5. Existing tests

All of `backend/tests/**` and `frontend/src/**/*.test.js` stay green without edits, except:

| File | Edit | Kind | Task |
|------|------|------|------|
| `backend/tests/test_b51.py:149` | `logger='backend.routers.fire'` becomes `logger='backend.modules.fire.http'` | dotted path of the moved module | T502 |
| `backend/tests/architecture/test_sql_ownership.py`, `module_map.py` | path strings and keys of moved files, if a test names one | file path of moved SQL | T502 |
| `backend/tests/test_b93_lifespan_shutdown.py` | the two lines that patch `main.fire_poller.run` and `main.fire_alarm.run` go; the first test starts one module task that fails on cancellation through a patched `main.MODULES` (real `start_module_tasks` and `stop_module_tasks`) and asserts: no exception leaves `lifespan`, `close_pool` was called, one ERROR record names the task. The second test keeps its assertion. | deliberate: the test pins wiring that this step moves | T503 |
| the frontend test files that move with their code (5 store tests, 2 lib tests, `FireAlarmBanner.test.js`, `FirePopup.test.js`, `fireLayers.test.js`) | relative import and `vi.mock` paths | import path | T505, T506, T508 |
| `frontend/src/platform/map-shell/BannerStack.test.js:34-42` | the cases `the legacy list puts SOS above fire and has no problem` and `a module banner with priority 15 lands between them` read `LEGACY_BANNERS` and expect `fire-alarm` in it; both take an inline two-item fixture list (`sos` at priority 10, `fire-alarm` at priority 20) instead, with the same expectations. The real order is asserted against the module list in `modules/fire/index.test.js` | deliberate: the list the cases read loses its fire line | T505 |
| `frontend/src/views/MapView.toggles.order.test.js:38` | `vi.mock('../composables/map/fireLayerList', ...)` becomes `vi.mock('../modules/fire/map/layers.js', ...)` | mock path | T506 |
| `frontend/src/composables/useWebSocket.test.js`, `useWebSocket.b66.test.js`, `useWebSocket.dispatch.test.js` | `vi.mock('../stores/fire', ...)` becomes `vi.mock('../modules/fire/store.js', ...)` | mock path | T510 |

`backend/tests/conftest.py` is not edited: `from backend.routers import fire` resolves to the alias. The 24 backend files that import `backend.fire.*` are not edited: `test_api_fire_alerts`, `test_api_fire_read`, `test_api_fire_writes`, `test_b47`, `test_b49`, `test_b51`, `test_b51_db`, `test_fire_alerts_db`, `test_fire_anonymise`, `test_fire_b46`, `test_fire_parse`, `test_fire_poller`, `test_fire_proximity`, `test_fire_repository`, `test_fire_service`, `test_fire_service_unit`, `test_fire_sources`, `test_fire_writes_db`, `test_settings_module`, `test_api_settings`, `test_users_api`, `test_devices_api`, `test_devices_db`, `test_users_db`.

## 6. Open to the owner and hand-offs

1. **Aliases or edited imports.** The plan keeps nine alias files until step 5 (9 approved lines, no test edited). The alternative is no alias and import-path edits in 24 test files. The plan follows the decision "old imports stay until step 5"; say so if the other way is wanted.
2. **Static imports in a manifest.** Wave 1 wrote "plain data and lazy components only". Fire's banner, popup container, panels and live handlers are imported statically, so the alarm is never behind a chunk load (BP-02) and the unedited tests see the children at once. The cost is entry chunk growth (fire store, banner, tone; no OpenLayers). If the entry chunk must stay flat, one more task adds a second entry file per module (`src/modules/uiEntries.js`, the pattern of `mapEntries.js`) and the manifests go back to data.
3. **`module_edges`** makes the direction of every call between modules a ratchet. After step 2 it holds four rows (`settings` twice, `users`, `devices` calling `fire.api`), all `until: 4`. Accept, or bring the events `HQCleared`, `PersonDeactivated`, `DeviceDeactivated` forward.
4. **Retention stays in `main.py`.** The spec moves it to `tracking.tasks` in step 3; four tests call `main._cleanup_old_locations()` and patch its names, and `allowlist.json` already says `until: 5` for its DELETE. This wave leaves the loop where it is.
5. **To the architecture owner (text proposals, not edited here):** modular-monolith.md 3.1 (where an actor that runs SQL lives: `infrastructure/`, started from `tasks.py`), 3.2 and 7 (panels with a host; the toggle state hook; static imports of a manifest), 8 (the `module_edges` ratchet as the import side of "only allowed directions"; the loader rule for route types).
6. **Zone texts of the Settings page** stay in the `settings.*` namespace (moving a key renames it); the zones section itself becomes fire's in T509.
7. `README.md` file tree (owner-written) does not show `backend/modules/fire/` or `frontend/src/modules/fire/`.

---

### Task 500: B96, the loader refuses a route type that cannot carry the auth dependency

**risk:** security
**owner:** implementer
**Files:**
- Modify: `backend/core/modules.py` (`HTTP_METHODS`, `_route_keys`, new `_unguardable_problems`, `check_modules`, `include_module_routers`)
- Modify: `backend/tests/architecture/rules.py` (`effective_routes`, `check_module_route_auth`)
- Modify: `backend/tests/modules/core/test_module_loader.py`, `backend/tests/architecture/test_route_auth.py` (tests appended)
- Modify: `docs/superpowers/plans/2026-10-31-vs-phase0-1.bugs.md` (status line of B96)

**Interfaces:**
- Consumes: `ModuleManifest.public_routes`, `include_module_routers(app, modules, *, auth)`.
- Produces in `core/modules.py`: `HTTP_METHODS` gains `'MOUNT'`. `_route_keys(route)` returns `{('MOUNT', path)}` for a `starlette.routing.Mount`, the method pairs for a route with `methods`, and `{('WEBSOCKET', path)}` for a WebSocket route. `_unguardable_problems(m: ModuleManifest) -> list[str]`: for every route of `m.router.routes`, **walked recursively through `effective_candidates()`** with its full prefixed path (FastAPI 0.142 keeps a nested `router.include_router(sub)` as one lazy `_IncludedRouter` with no path and no methods, so a flat loop never sees a `Mount` inside it), that is not a `fastapi.routing.APIRoute` or `fastapi.routing.APIWebSocketRoute` and whose keys are not all in `m.public_routes`, the message `'<module>: <path> is a <TypeName>, which cannot carry the auth dependency: serve it from an endpoint or declare it in public_routes'`. `check_modules` includes these problems, so `include_module_routers` raises `ValueError('invalid module list: ...')` before it mounts anything. A declared public `Mount` is added with `app.mount(route.path, route.app, name=route.name)`; a declared public plain route with `app.router.routes.append(route)`.
- Produces in `rules.py`: `effective_routes` yields a `Mount` as one `EffectiveRoute` with the method `MOUNT` **before** it flattens the mounted application (a `StaticFiles` app has no `routes`, so today such a mount contributes nothing and cannot be reported); the routes of a mounted sub-application are still listed after it. `check_module_route_auth` also reports a `Mount`, a plain `Route` and a plain `WebSocketRoute` of a module router that is in the route table and not declared public (`'<module>: <path> (<TypeName>) is served without the auth dependency'`), and one that is not in the route table at all (`'not mounted'`).

- [ ] **Step 1: Write the failing tests**, tagged `Trait("Bug", "B96")`. In `test_module_loader.py`: `test_a_mount_without_a_public_declaration_is_refused` (a manifest whose router has `router.mount('/files', StaticFiles(directory=tmp_path))`; `pytest.raises(ValueError, match='cannot carry the auth dependency')`; `app.routes` is unchanged); `test_a_plain_starlette_route_is_refused` (`router.add_route('/raw', endpoint)`; same); `test_a_mount_inside_a_nested_include_is_refused` (`sub.mount('/files', StaticFiles(...))` and `router.include_router(sub, prefix='/api/x')`; the same `ValueError`, and the message names `/api/x/files`); `test_a_public_mount_is_served` (`public_routes=(('MOUNT', '/files'),)`; a file written to `tmp_path` is answered with 200 by `TestClient`, without a token); `test_api_routes_next_to_a_public_mount_keep_auth` (the same router also has `GET /api/x/data`; without a token it answers 401). In `test_route_auth.py`: `test_a_mount_added_around_the_loader_is_reported` (`app.include_router(router)` and `app.mount(...)` by hand; the problems name `/files` and `Mount`); `test_effective_routes_lists_a_static_mount` (a `StaticFiles` mount, and one inside a nested include, each appear with the method `MOUNT` and the full path).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\core\test_module_loader.py backend\tests\architecture\test_route_auth.py -q --task B96`. Expected: FAIL (the mount is accepted, or it is not served at all: the output says which, write it into the PR body).
- [ ] **Step 3: Implement** the interfaces. The kernel still imports nothing from `backend.modules` or `backend.auth`.
- [ ] **Step 4: Run** the loader, route and architecture tests and the suites that import `main`. Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\core backend\tests\architecture backend\tests\modules\settings -q`. Expected: PASS.
- [ ] **Step 5: Commit** `fix(core): B96 the module loader refuses a mount or plain route without a public declaration`; set the B96 status in the bugs file to `fixed` with the branch name.

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\core backend\tests\architecture backend\tests\modules\settings -q`

### Task 501: direction ratchet, calls between modules follow the allowed edges

**risk:** normal
**owner:** implementer
**Files:**
- Modify: `backend/tests/architecture/rules.py` (new `module_edge_violations`), `backend/tests/architecture/allowlist.json` (new key `"module_edges": []`)
- Create: `backend/tests/architecture/test_module_edges.py`

**Interfaces:**
- Consumes: `rules.ALLOWED_EDGES`, `module_map.owners_of`, `grimp` (installed with import-linter), `approved_additions.APPROVED`, `test_ratchet.growth_verdict` (it already counts every list of `allowlist.json`).
- Produces `rules.module_edge_violations(imports: Iterable[tuple[str, str]]) -> set[tuple[str, str]]`: of the direct imports `(importer, imported)` it returns those where `imported` is `backend.modules.<X>` or below and none of these holds: the importer is inside `backend.modules.<X>`; the importer's owners (`backend.modules.<M>` gives `M`; any other file through `module_map.owners_of`) contain `X`; an owner `O` has `(O, X)` in `ALLOWED_EDGES`; the importer has no owner or the owner `core` (`main.py`, `modules/registry.py`, `modules/__init__.py`, `core/**`).
- Produces in `allowlist.json`: `module_edges`, a list of `{"from": "<importer>", "to": "<imported>", "until": <step>}`; empty after this task.
- Produces tests that later tasks only feed with data: `test_real_module_edges_match_the_allowlist_exactly` (a new violation fails with `add the edge to ALLOWED_EDGES or carry it in module_edges with an approval`; a stale row fails with `delete this row`), `test_module_edge_rows_are_not_overdue` (`until > completed_step`).

- [ ] **Step 1: Write the failing tests**, tagged `T501`: `test_direction_rule_bites` (imports given as data: `('backend.routers.users', 'backend.modules.fire.api')` is a violation (`people` to `fire`); `('backend.fire.repository', 'backend.modules.fire.infrastructure.repository')` is not (same owner); `('backend.hardware_reader.reader', 'backend.modules.tracking.api')` is not (`gateway` to `tracking` is allowed); `('backend.main', 'backend.modules.fire.api')` is not (assembly); `('backend.modules.settings.http', 'backend.modules.fire.api')` is a violation; `('backend.routers.locations', 'backend.modules.sos.http')` is not (owner `sos`)); `test_real_module_edges_match_the_allowlist_exactly`; `test_module_edge_rows_are_not_overdue`; `test_the_graph_sees_function_level_and_lazy_imports` (the grimp graph of `backend` contains `backend.main -> backend.hardware_reader.hid_reader` and `backend.modules -> backend.modules.registry`).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\architecture\test_module_edges.py -q`. Expected: FAIL with `AttributeError: module 'backend.tests.architecture.rules' has no attribute 'module_edge_violations'`.
- [ ] **Step 3: Implement.** The real list is empty today (the only module, `settings`, imports the legacy package `backend.fire`, which is not under `backend.modules`).
- [ ] **Step 4: Run** the directory. Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\architecture -q`. Expected: PASS.
- [ ] **Step 5: Commit** `test(architecture): T501 calls between modules follow the allowed edges`.

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\architecture -q`

### Task 502: backend `fire` module, the move

**risk:** security
**owner:** implementer
**Files:**
- Move (`git mv`): the nine files of section 1.1 into `backend/modules/fire/domain/`, `infrastructure/` and `http.py`
- Create: `backend/modules/fire/__init__.py` (docstring), `domain/__init__.py`, `infrastructure/__init__.py`, `module.py`, `api.py` (docstring only in this task)
- Create: the nine alias files at the old paths (template of the settings plan, section 1.3); `backend/fire/__init__.py` stays
- Modify: `backend/modules/registry.py` (`from .fire.module import manifest as fire_manifest`; `MODULES = (fire_manifest, settings_manifest)`)
- Modify: `backend/main.py` (the name `fire` leaves the `from .routers import` line; `app.include_router(fire.router)` is deleted)
- Modify: `backend/tests/architecture/importlinter.toml`, `approved_additions.py`
- Modify: `backend/tests/architecture/rules.py` (`_ignore_import_problems`), `backend/tests/architecture/test_manifest.py` (two tests appended)
- Modify: `tools/smoke.py`, `backend/tests/test_smoke_script.py`, `docs/SMOKE.md` (step h)
- Modify: `backend/tests/test_b51.py:149` (logger name)
- Create: `backend/tests/modules/fire/__init__.py`, `backend/tests/modules/fire/test_fire_module.py`

**Interfaces:**
- Consumes: the loader (T400, T500), `check_boundary_contracts`, `check_manifest_wiring`, `module_edge_violations` (T501).
- Produces: every moved file keeps its content; only its relative imports change (`..database` becomes `...core.database` or `....core.database`, `from . import repository` inside `infrastructure/` stays, `from .parse import ...` becomes `from ..domain.parse import ...`, `sources.py` imports `....version`).
- Produces `http.py`: `router = APIRouter(prefix='/api/fire', tags=['fire'])` with the 15 endpoint functions, the request models and the module attributes the tests patch, under their present names: `logger`, `poller`, `repository`, `notify`, `notify_data_changed`, `fire_alarm`, `is_storable`.
- Produces `module.py`: `manifest = ModuleManifest(name='fire', owns_tables=('fire_hotspots', 'fire_burnt_areas', 'fire_alerts', 'fire_suppression_zones'), reads_tables=('devices', 'location_events', 'settings', 'users'), router=http.router, live_messages=('fire_data_updated', 'fire_alert', 'fire_alert_repeat', 'fire_alert_updated', 'fire_zones_updated'))`; no `public_routes`, no `tasks` yet (T503).
- Produces in `importlinter.toml`: the 8 lines of section 1.1 are gone; `boundary-settings` gains `"backend.modules.fire"` in `source_modules`; new contract `id = "boundary-fire"`, `name = "module boundary: fire"`, `type = "forbidden"`, `source_modules` = `rules.LEGACY_SOURCES` plus `"backend.modules.settings"`, `forbidden_modules = ["backend.modules.fire.domain", "backend.modules.fire.http", "backend.modules.fire.infrastructure", "backend.modules.fire.module"]`, `allow_indirect_imports = true`, `ignore_imports` = the nine alias edges (`"backend.fire.models -> backend.modules.fire.domain.models"` and so on, `"backend.routers.fire -> backend.modules.fire.http"`), one per line, each `# until step 5`. Nine `APPROVED` entries with the reason "old import path kept as an alias until step 5; 24 test files import it".
- Produces in `rules.py`: `_ignore_import_problems` accepts a target that is a private child **or a module below one** (`imported == child or imported.startswith(child + '.')` for a `child` of `private`); the importer rule and the wildcard rule are unchanged. Today it accepts the direct child only, so `backend.fire.models -> backend.modules.fire.domain.models` is refused with `may only open an import into a private child`; without this edit `test_manifest.py:100` fails.
- Produces in `tools/smoke.py`: step `'h. GET /api/fire/status = 200'`, `needs=('c. admin login + token refresh',)`, after step g; `s_fire` expects 200 and a JSON object with the key `feeds`.

- [ ] **Step 1: Write the failing tests** in `test_fire_module.py`, tagged `T502`: `test_old_paths_are_the_new_modules` (parametrised over the nine pairs: `importlib.import_module(old) is importlib.import_module(new)`, and `from backend.fire import repository as via_pkg` is the new module); `test_importing_an_old_path_first_works` (subprocess per old path, `cwd=REPO`: `import <old> as m; print(m.__name__)` prints the new name and exits 0); `test_state_is_shared_through_the_alias` (`backend.fire.poller.FEEDS is backend.modules.fire.infrastructure.poller.FEEDS`; `backend.fire.service.service is backend.modules.fire.infrastructure.service.service`); `test_manifest` (name, the four owned tables, the five live messages, `manifest.router is http.router`, `public_routes == ()`, `manifest in backend.modules.MODULES`, fire is listed before settings); `test_fire_routes_are_served_once_by_the_real_app` (each `(path, methods)` of `http.router` appears exactly once in `backend.main.app.routes`); `test_fire_routes_keep_their_place` (the first `/api/fire` route comes after the last `/api/export` route and before the first `/api/settings` route); `test_every_fire_route_needs_a_login` (`TestClient(backend.main.app)` without lifespan: every fire path answers 401 without a token); `test_openapi_operation_ids_are_unchanged` (the operation ids of the 15 fire operations equal a literal list taken from `app.openapi()` on `develop` before the move; the executor generates the list first and pastes it); `test_main_no_longer_mounts_the_fire_router` (the text of `backend/main.py` has no `fire.router`); `test_domain_is_pure` (the files of `domain/` import none of `asyncpg`, `httpx`, `fastapi`, checked with `ast`). In `test_manifest.py`, next to the existing `check_boundary_contracts` cases and with their `_complete_toml` helper, tagged `T502`: `test_an_ignore_entry_may_open_a_file_below_a_private_child` (`backend.routers.x -> backend.modules.a.infrastructure.repo` gives no problem) and `test_an_ignore_entry_into_another_module_or_a_look_alike_is_still_refused` (the targets `backend.modules.b.infrastructure.repo`, `backend.modules.a.api` and `backend.modules.a.infrastructure_extra` each give `may only open an import into a private child`). In `test_smoke_script.py`: `test_fire_step_passes_on_200_with_feeds` and `test_fire_step_fails_on_500`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\fire -q`. Expected: FAIL with `ModuleNotFoundError: No module named 'backend.modules.fire'`. Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\architecture\test_manifest.py -q --task T502`. Expected: FAIL (`may only open an import into a private child`).
- [ ] **Step 3: Move.** `git mv` each file, repoint its imports, write the nine aliases, `module.py`, the registry line, the two `main.py` edits, the logger string in `test_b51.py`, the smoke step.
- [ ] **Step 4: Extend, then shrink the allowlist.** Widen `_ignore_import_problems` first. Add the contract, the nine alias lines and their approvals by hand, then run `.venv\Scripts\python backend\tests\architecture\regen.py --remove-stale` (it deletes the 8 stale lines and nothing else: check the diff). Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\architecture -q`. Expected: PASS, including `test_every_contract_bites[module boundary: fire]`, `domain is pure`, `test_no_sql_outside_infrastructure_in_the_real_modules` and `test_real_module_edges_match_the_allowlist_exactly` (still empty: the callers import `backend.fire.*`).
- [ ] **Step 5: Run** the module tests and every unedited fire test. Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_smoke_script.py backend\tests\test_api_fire_alerts.py backend\tests\test_api_fire_read.py backend\tests\test_api_fire_writes.py backend\tests\test_api_settings.py backend\tests\test_b47.py backend\tests\test_b49.py backend\tests\test_b51.py backend\tests\test_b93_lifespan_shutdown.py backend\tests\test_fire_anonymise.py backend\tests\test_fire_parse.py backend\tests\test_fire_poller.py backend\tests\test_fire_proximity.py backend\tests\test_fire_repository.py backend\tests\test_fire_service_unit.py backend\tests\test_fire_sources.py -q`. Expected: PASS.
- [ ] **Step 6: Commit** `refactor(fire): T502 fire becomes a backend module behind aliases`. PR body: files moved, nine aliases, the nine logger names, the allowlist arithmetic (8 deleted, 9 added, reasons).

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_smoke_script.py backend\tests\test_api_fire_alerts.py backend\tests\test_api_fire_read.py backend\tests\test_api_fire_writes.py backend\tests\test_api_settings.py backend\tests\test_b47.py backend\tests\test_b49.py backend\tests\test_b51.py backend\tests\test_b93_lifespan_shutdown.py backend\tests\test_fire_anonymise.py backend\tests\test_fire_parse.py backend\tests\test_fire_poller.py backend\tests\test_fire_proximity.py backend\tests\test_fire_repository.py backend\tests\test_fire_service_unit.py backend\tests\test_fire_sources.py -q`

### Task 503: `fire.api`, its callers, the fire tasks and the `main.py` wiring

**risk:** security
**owner:** implementer
**Files:**
- Modify: `backend/modules/fire/api.py`, `module.py`; create `backend/modules/fire/tasks.py`
- Modify: `backend/modules/fire/infrastructure/repository.py` (one new function and `ALARM_LOCK_KEY`), `infrastructure/service.py` (the key becomes a re-export)
- Modify: `backend/routers/users.py:19-20`, `backend/routers/devices.py:11-12,206-239`, `backend/modules/settings/http.py:10-11`, `backend/modules/settings/infrastructure/publisher.py:4,13`
- Modify: `backend/main.py` (lines 24 to 26, 178 to 183, 211 to 212, 220 to 222)
- Modify: `backend/tests/architecture/importlinter.toml`, `allowlist.json`, `approved_additions.py`
- Modify: `backend/tests/test_b93_lifespan_shutdown.py` (section 5)
- Create: `backend/tests/modules/fire/test_fire_api.py`

**Interfaces:**
- Consumes: T502; `start_module_tasks`, `stop_module_tasks`, `_log_task_failure` of `main.py`.
- Produces `api.py`, the only file other code imports. Every function is a thin pass-through that looks its implementation up at call time (`repository.resolve_hq_alerts(*args, **kwargs)`, never `from .infrastructure.repository import resolve_hq_alerts`):
  - `ALARM_LOCK_KEY` (the constant; it moves to `repository.py`, see below)
  - `request_evaluation() -> None` (calls `service.service.request_evaluation()`)
  - `async resolve_hq_alerts(*args, **kwargs)`, `async resolve_disabled_alerts(*args, **kwargs)`, `async get_alert_out(*args, **kwargs)` (repository)
  - `async notify(conn, channel, payload)`, `async notify_alerts_updated(conn, alert_ids)` (service module)
  - `async lock_and_resolve_device_alerts(conn, device_id, actor_id) -> list[Record]`
  - `async anonymise_alerts(*args, **kwargs)`, `async anonymise_hotspots(*args, **kwargs)`, `async prune_fire_data(*args, **kwargs)` (repository)
- Produces in `repository.py`: `ALARM_LOCK_KEY = 7_342_102` is defined here and `service.py` keeps the name with `ALARM_LOCK_KEY = repo.ALARM_LOCK_KEY` (`service.py` imports `repository`, so a repository function that read the key from `service` would be a circular import; three test files import `backend.fire.service.ALARM_LOCK_KEY`). `async lock_and_resolve_device_alerts(conn, device_id, actor_id) -> list[Record]`: the three statements of `devices.py:216-224` unchanged and in that order on the given connection (`SET LOCAL lock_timeout = '10s'`, `SELECT pg_advisory_xact_lock($1)` with `ALARM_LOCK_KEY`, the `UPDATE fire_alerts ... RETURNING id::text`), returning the rows of the UPDATE as they come. It opens no transaction and catches nothing: `LockNotAvailableError` reaches the caller's `except`.
- Produces `tasks.py`: `async poll_feeds() -> None` (sets `poller.after_refresh = service.service.request_evaluation`, then `await poller.run()`) and `async alarm_loop() -> None` (`await service.service.run()`). `module.py`: `tasks=(tasks.poll_feeds, tasks.alarm_loop)`; `boundary-fire` gains `"backend.modules.fire.tasks"` in `forbidden_modules`.
- Produces in the callers (the local names stay, because tests patch them by dotted string): `users.py`: `from ..modules.fire import api as fire_repository` and `from ..modules.fire.api import notify_alerts_updated`; `devices.py`: `from ..modules.fire import api as fire_repository` and `from ..modules.fire.api import notify as fire_notify, notify_alerts_updated`; `settings/http.py`: `from ..fire import api as fire_repository` and `from ..fire.api import notify_alerts_updated`; `publisher.py`: `from ...fire import api as fire_api` and `fire_api.request_evaluation()`. `devices.py`, permanent delete: only the lock and the UPDATE (lines 216 to 224) become `resolved = await fire_repository.lock_and_resolve_device_alerts(conn, device_id, user['id'])` inside the same transaction at the same place. The loop after the `try` (lines 235 to 241: `fire_repository.get_alert_out`, `fire_notify`, the per-alert warning) is **not edited**: four tests of `test_api_fire_alerts.py` (lines 142-143, 201, 216-217) patch `devices.fire_notify` and `devices.fire_repository.get_alert_out` and read the `('notify', 'fire_alert_updated', ...)` record, so replacing the loop with `notify_alerts_updated` would break them or leave their patches testing nothing. Only the import of `ALARM_LOCK_KEY` goes.
- Produces in `main.py`: line 25 becomes `from .modules.fire.api import anonymise_alerts, anonymise_hotspots, prune_fire_data`; lines 24 and 26 go; in `lifespan` the lines that create `fire_task` and `alarm_task`, assign `after_refresh`, cancel both and await `alarm_task` go. `_cleanup_old_locations` is not edited.
- Produces in the allowlists: the 10 `fire-private` lines of section 1.1 and their 3 approvals are gone; the contract `fire-private` stays with an empty `ignore_imports` (no production file imports the alias package any more); `module_edges` holds four rows (`backend.modules.settings.http`, `backend.modules.settings.infrastructure.publisher`, `backend.routers.users`, `backend.routers.devices`, each to `backend.modules.fire.api`, `until: 4`) with four approvals; the `sql_writes` row of `routers/devices.py` for `fire_alerts` is gone; `completed_step` is 2.

- [ ] **Step 1: Write the failing tests** in `test_fire_api.py`, tagged `T503`: `test_the_device_delete_broadcast_still_goes_through_the_names_of_devices` (`inspect.getsource(devices.delete_device_permanent)` still calls `fire_notify(` and `fire_repository.get_alert_out(`; `devices.fire_notify` exists); `test_the_alarm_lock_key_is_one_value` (`repository.ALARM_LOCK_KEY`, `service.ALARM_LOCK_KEY`, `api.ALARM_LOCK_KEY` and `backend.fire.service.ALARM_LOCK_KEY` are equal, and `import backend.modules.fire.infrastructure.repository` as the first import of a fresh interpreter exits 0); `test_api_looks_the_implementation_up_at_call_time` (parametrised over the eight pass-through names: after `monkeypatch.setattr(<repository or service module>, name, fake)` the api function calls `fake` with the same arguments); `test_request_evaluation_reaches_the_service_instance` (`monkeypatch.setattr(service.service, 'request_evaluation', ...)`); `test_device_delete_keeps_the_statement_order` (mocked connection through `DELETE /api/devices/{id}/permanent`: the texts of `conn.execute` and `conn.fetch` come in the order `DELETE FROM sos_alerts`, `DELETE FROM location_events`, `DELETE FROM repeater_events`, `SET LOCAL lock_timeout`, `pg_advisory_xact_lock`, `UPDATE fire_alerts`, and `DELETE FROM devices` after them, all inside one `conn.transaction()`); `test_a_busy_alarm_lock_still_answers_503` (`conn.execute` raises `asyncpg.exceptions.LockNotAvailableError` on the lock statement: 503, the detail text of today); `test_fire_tasks_are_in_the_manifest` (`[t.__name__ for t in manifest.tasks] == ['poll_feeds', 'alarm_loop']`, `rules.check_manifest_wiring` is `[]`); `test_poll_feeds_wires_the_alarm_before_the_first_refresh` (`poller.run` replaced by a coroutine that records `poller.after_refresh`: it is `service.service.request_evaluation`); `test_fire_tasks_are_stopped_before_the_pool_closes` (the real `lifespan` with `init_pool`, `_run_migrations`, `_ensure_default_admin`, `close_pool`, the readers and the listener replaced as in the B93 test, and `poller.run` and `service.service.run` replaced by coroutines that record their cancellation: both recorded it before `close_pool` was called); `test_a_crashed_fire_task_is_logged_by_name` (`service.service.run` raises `RuntimeError('x')`: one ERROR record contains `fire.alarm_loop`); `test_main_names_no_fire_internals` (`backend/main.py` parsed with `ast`, not searched as text, because `modules.fire.api` itself contains `.fire.`: no `ImportFrom` has the module `fire`, `routers.fire` or one that starts with `fire.`, and none imports the name `fire` from `routers`; no name `fire_poller` or `fire_alarm` is bound or read; exactly one `ImportFrom` has the module `modules.fire.api`); `test_no_production_file_imports_the_old_fire_package` (grimp: no importer of `backend.fire` or below outside `backend.fire` itself).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\fire\test_fire_api.py -q`. Expected: FAIL with `AttributeError: module 'backend.modules.fire.api' has no attribute 'request_evaluation'`.
- [ ] **Step 3: Implement** the api, the repository function, the tasks, the caller edits, the `main.py` edits and the rewrite of the B93 test (section 5).
- [ ] **Step 4: Shrink and carry the allowlists.** Add the four `module_edges` rows and approvals, then `regen.py --remove-stale`, delete the three stale approvals and the SQL row, set `completed_step` to 2. Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\architecture -q`. Expected: PASS.
- [ ] **Step 5: Run** the DoD list. Expected: PASS.
- [ ] **Step 6: Commit** `refactor(fire): T503 callers use fire.api and the fire tasks come from the manifest`. PR body: the allowlist arithmetic (10 lines and 1 row deleted, 4 rows added, reasons), the changed shutdown behaviour and the two new task names in the log.

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_api_fire_alerts.py backend\tests\test_api_fire_writes.py backend\tests\test_api_settings.py backend\tests\test_api_devices.py backend\tests\test_api_users.py backend\tests\test_b47.py backend\tests\test_b51.py backend\tests\test_b93_lifespan_shutdown.py backend\tests\test_fire_anonymise.py backend\tests\test_fire_poller.py backend\tests\test_fire_service_unit.py backend\tests\test_startup_migrations.py backend\tests\test_simulation.py -q`

### Task 504: panel contribution point and the toggle state hook

**risk:** normal
**owner:** frontend-designer
**Files:**
- Modify: `frontend/src/platform/manifest.js` (`panelProblems`, `toggleProblems`), `frontend/src/platform/map-shell/contributions.js` (`PANEL_HOSTS`, `collectPanels`, a duplicate panel id in `contributionProblems`)
- Create: `frontend/src/platform/PanelHost.vue`, `frontend/src/platform/PanelHost.test.js`
- Modify: `frontend/src/platform/map-shell/contributions.test.js`, `frontend/src/platform/manifest.test.js` (tests appended)
- Modify: `frontend/src/views/MapView.vue` (three host tags, `mapContext`, the toggle buttons)

**Interfaces:**
- Consumes: the collectors of T420, `BannerStack.vue` (its error boundary is the model), the facade object returned by `useMap`.
- Produces the contract additions of section 1.2 (`panels` with `host` and `order`, `collectPanels`, `toggle.key`, `toggle.isOn`, `toggle.set`).
- Produces `PanelHost.vue`: props `panels` (collected list) and `context` (object); it renders each `component` with `:context="context"` and `:key="id"`, adds no element of its own, and a panel that throws while rendering is logged as `console.error('panel <id> failed', error)` and renders nothing from then on while the others stay. A panel with `retryKey` is the exception: the host watches `retryKey(context)` and clears the failed mark of that panel when the value changes, so the next render tries it again (the SOS toast of the tracking plan uses it: one render error must not hide every later toast). `validateManifest` accepts `retryKey` only as a function. Test: `a failed panel with a retryKey is rendered again when the key changes, one without it is not [T504]`.
- Produces in `MapView.vue`: `const mapContext = { hostMap, facade, mapKit, isAdmin, activeBasemap, mapActive, selectedDeviceId, closeContextMenu: () => ctxMenu.value?.close() }` where `facade` is the object `useMap` returned, `mapKit = { Overlay, fromLonLat, toLonLat, unByKey }` holds the four OpenLayers names `MapView.vue` already imports (so a panel or popup that a manifest imports statically needs no OpenLayers import of its own), `hostMap` is the `shallowRef` of T424 (it is `null` until the view's own `onMounted`, and a panel is mounted before that: a panel that needs the map watches `context.hostMap`, as `MapPopupHost.vue` watches its `map` prop) and the other refs are passed as refs; `<PanelHost :panels="collectPanels(MODULES, 'map-root')" :context="mapContext" />` as the first root node (before `<SOSToast />`), one for `'map-toolbar'` as the last child of `.basemap-switcher`, one for `'map'` as the last child of `.map-layout`. The toggle buttons render `:data-layer="toggle.key"`, `active` and `aria-pressed` from `toggle.isOn()` and call `toggle.set(!toggle.isOn())` for a toggle that has the pair; for a toggle without it the present path through `LEGACY_LAYER_NAMES` stays (it is removed in T507).

- [ ] **Step 1: Write the failing tests**, each `[T504]`. `contributions.test.js`: `panels of one host come out by order, then id` (hosts `map` and `settings` mixed; `collectPanels(modules, 'map')` gives only the `map` items in order); `a panel without a host is in no host list`; `contributionProblems names a duplicate panel id`. `manifest.test.js`: `validateManifest accepts host, order and the toggle pair and names each malformed one` (host `'nowhere'`, order `'1'`, `isOn` without `set`, `key` that is not text). `PanelHost.test.js`: `renders the panels in order without a wrapper and hands each the context`; `a panel that throws is skipped and logged once, the others stay`; `an empty list renders nothing`. `MapView.panels.test.js` (new file, the mock set-up of `MapView.fire.test.js` copied): `a module panel of host map is rendered inside the map layout with the context` (`vi.mock('../modules', ...)` adds one fixture manifest; its stub receives `context.facade` with `setHotspots` and `context.mapKit` with the four names); `a toggle with a state pair is driven by it` (fixture toggle: the button has its `data-layer`, the class `active` follows `isOn()`, a click calls `set(true)`).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/platform src/views/MapView.panels.test.js`. Expected: FAIL (`collectPanels is not a function`, `Failed to resolve import "./PanelHost.vue"`).
- [ ] **Step 3: Implement** the contract, the host and the three tags.
- [ ] **Step 4: Run** the seven unedited `MapView` test files, the platform tests and the module checks. Run: `cd bee-with-me\frontend; npm test -- src/platform src/views src/modules src/architecture.test.js; npm run build`. Expected: PASS and a clean build. If a name stub does not reach a component under `PanelHost`, render the panels through a `v-for` in the host's parent and keep `PanelHost` for the boundary only; say so in the PR body.
- [ ] **Step 5: Commit** `feat(map): T504 panels with a host and a state hook for layer toggles`.

dod:
- `cd bee-with-me\frontend; npm test -- src/platform src/views src/modules src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`

### Task 505: frontend `fire` module, part 1 (store, libs, alarm banner, texts)

**risk:** normal
**owner:** frontend-designer
**Files:**
- Move (`git mv`): `stores/fire.js` and its five tests to `modules/fire/store.js` and `modules/fire/store*.test.js`; `lib/fireErrors.js`, `lib/fireStyle.js`, `lib/fireTone.js` and their tests to `modules/fire/lib/`; `components/FireAlarmBanner.vue` and its test to `modules/fire/components/`
- Create: `frontend/src/modules/fire/index.js`, `modules/fire/i18n/en.js`, `modules/fire/i18n/bg.js`, `modules/fire/index.test.js`
- Create (re-exports, one statement each): `frontend/src/stores/fire.js`, `frontend/src/lib/fireErrors.js`, `frontend/src/lib/fireStyle.js`
- Modify: `frontend/src/modules/index.js` (one line, alphabetical), `frontend/src/i18n/en.js`, `bg.js` (the namespaces `fire` and `fireAlarm` leave), `frontend/src/components/legacyBanners.js` (the fire line leaves)
- Modify: `frontend/src/platform/map-shell/BannerStack.test.js` (two cases, section 5)

**Interfaces:**
- Consumes: `BANNER_PRIORITY` (T420), `collectBanners` and `contributionProblems` (T420, T421), the module assembly of T403.
- Produces `modules/fire/index.js`: `export default { name: 'fire', routes: [], nav: [], mapLayers: [], panels: [], banners: [{ id: 'fire-alarm', priority: BANNER_PRIORITY.fireAlarm, component: FireAlarmBanner }], liveHandlers: {}, i18n: { en, bg }, depends: [] }` and the named export `useFireStore` (re-exported from `./store.js`): `index.js` is the module's public face for code outside it.
- Produces the re-exports: `export * from '../modules/fire/store.js'` and the two lib files likewise. `lib/fireTone.js` gets none (its only importers move).

- [ ] **Step 1: Check the mocks, then write the failing tests.** Run `git grep -n "vi.mock('[^']*\(stores/fire\|lib/fire\)" -- frontend/src`: the three `useWebSocket` tests mock `../stores/fire` and `useWebSocket.js` keeps importing that path, so they stay as they are; `FireAlarmBanner.test.js` mocks `../lib/fireTone`, which resolves to the moved lib from its new folder. Tests in `modules/fire/index.test.js`, each `[T505]`: `the fire manifest is valid and is in the module list`; `the fire banner is a manifest contribution below SOS` (`collectBanners(MODULES, LEGACY_BANNERS).map(b => b.id)` equals `['sos', 'fire-alarm']`; `contributionProblems(MODULES, { banners: LEGACY_BANNERS })` is `[]`; the fire item's `component` is the banner component itself, not a function); `the old store path is the same store` (`useFireStore` imported from `stores/fire.js` and from `modules/fire/index.js` is one function); `the fire texts are in the merged dictionaries in both languages` (`fire.asOf` and `fireAlarm` keys of the snapshot exist in EN and BG). That the manifest reaches no OpenLayers needs no test of its own: `modules.test.js:215` scans every module's `index.js` and is in this task's DoD.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/modules/fire/index.test.js`. Expected: FAIL (`Failed to resolve import "./index.js"`).
- [ ] **Step 3: Move** the files, repoint their imports, cut the two namespaces out of the core dictionaries into the module dictionaries, write the manifest, the list line and the three re-exports, delete the fire line of `legacyBanners.js`.
- [ ] **Step 4: Run** everything that imports a moved file. Run: `cd bee-with-me\frontend; npm test -- src/modules src/components src/composables src/views src/platform src/i18n src/architecture.test.js; npm run build`. Expected: PASS and a clean build; `no text key was lost`, `no key is defined twice` and the EN/BG parity test of `modules.test.js` pass. Write the entry chunk size before and after into the PR body.
- [ ] **Step 5: Commit** `refactor(fire): T505 fire store, libs, texts and the alarm banner move into the fire module`.

dod:
- `cd bee-with-me\frontend; npm test -- src/modules src/components src/composables src/views src/platform src/i18n src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`

### Task 506: the fire map entry and its layer declarations

**risk:** normal
**owner:** frontend-designer
**Files:**
- Move (`git mv`): `composables/map/fireLayerList.js` to `modules/fire/map/layers.js`; `composables/map/fireLayers.js` and its test to `modules/fire/map/index.js` and `modules/fire/map/fireLayers.test.js`
- Modify: `frontend/src/modules/fire/index.js` (`mapLayers`), `frontend/src/modules/mapEntries.js`
- Modify: `frontend/src/composables/useMap.js` (lines 32, 33, 392 to 394, 853 to 860), `frontend/src/views/MapView.vue` (lines 337 and 493)
- Modify: `frontend/src/views/MapView.toggles.order.test.js:38` (mock path)

**Interfaces:**
- Consumes: `shell.install` and the `ctx` of T422 (unchanged), the install loop over `MAP_MODULES` in `useMap.js` (T427).
- Produces `map/layers.js`: `FIRE_MAP_LAYERS` as it is. `map/index.js`: the default export `{ name: 'fire', layers: {...}, setup: setupFireMap }` (today's `LEGACY_FIRE_MAP` under the entry shape; the named export goes). Manifest: `mapLayers: FIRE_MAP_LAYERS`. `mapEntries.js`: `MAP_MODULES = [fireMap, settingsMap]`.
- Produces in `useMap.js`: the legacy install line and the two imports are gone; the five fire names read `moduleApis.fire` at call time (`const fireApi = () => moduleApis.fire ?? {}`; `setHotspots = (fc) => fireApi().setHotspots?.(fc) ?? false`, and so on), so they work before mount and a failed install still gives `false` and no-ops. In `MapView.vue`: `collectLayerToggles(MODULES)` without a legacy list.

- [ ] **Step 1: Read, then write the failing tests.** Read `useMap.interaction.test.js`, `useMap.fire.test.js`, `useMap.zones.test.js` and the two `MapView.toggles*.test.js` files. Tests in `modules/fire/map/fireLayers.test.js` (appended), each `[T506]`: `the fire manifest declares the three layers and the entry has a factory for each` (ids `fire-burnt`, `fire-zones`, `fire-hotspots`; the keys of the entry's `layers` equal them); `the facade has no fire install of its own` (the text of `useMap.js` contains neither `fireLayers` nor `fireLayerList`); `MAP_MODULES lists fire and settings`; `the fire toggles come from the manifest alone` (`collectLayerToggles(MODULES).map(t => t.id)` equals `['fire-burnt', 'fire-hotspots', 'fire-zones']`).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/modules/fire/map`. Expected: FAIL (`Failed to resolve import "./index.js"`).
- [ ] **Step 3: Move** the two files, wire the manifest, the entry list, the facade and the one line of `MapView.vue`; edit the mock path.
- [ ] **Step 4: Run** the unedited interaction, fire and zone tests of the facade first: they pin the cursor and click precedence between a tracker and a hotspot, which now depends on the handlers' `order` and no longer on the place of the install line. If `a tracker under the pointer wins over a hotspot at the same pixel` or `a hotspot under the pointer sets the pointer cursor` fails, give the fire pointer handler an explicit `order` and say so in the PR body. Run: `cd bee-with-me\frontend; npm test -- src/modules src/composables src/views src/platform src/architecture.test.js; npm run build`. Expected: PASS and a clean build; the entry chunk has not grown by OpenLayers.
- [ ] **Step 5: Commit** `refactor(fire): T506 the fire layers are the fire module's map entry`.

dod:
- `cd bee-with-me\frontend; npm test -- src/modules src/composables src/views src/platform src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`

### Task 507: fire layer state, pill, attribution and focus ring leave the map view

**risk:** normal
**owner:** frontend-designer
**Files:**
- Create: `frontend/src/modules/fire/components/FireMapPanel.vue`, `frontend/src/modules/fire/ui.js`, `frontend/src/modules/fire/components/FireMapPanel.test.js`
- Modify: `frontend/src/modules/fire/index.js` (`panels`, the `toggle` pair of the three layers), `frontend/src/modules/fire/map/layers.js` (`toggle.key`)
- Modify: `frontend/src/views/MapView.vue` (template lines 88 to 91 and 103 to 116; script lines 491 to 504, 509 to 521, 680 to 690, the fire lines of the first `onMounted`, lines 711 to 715, 1200 to 1219, the focus lines of `onUnmounted`)

**Interfaces:**
- Consumes: the `map` host and `toggle` pair of T504; `mapContext` (`hostMap`, `facade`, `mapKit`, `isAdmin`, `mapActive`); the fire store.
- Constraint: `FireMapPanel.vue` and `ui.js` are imported statically by the manifest, so neither imports an `ol` module. The focus overlay is `new context.mapKit.Overlay(...)` and the coordinate conversion is `context.mapKit.fromLonLat`; the unedited `no manifest imports OpenLayers, directly or through static imports [T403]` of `modules.test.js` is the proof and is part of this task's DoD.
- Produces `ui.js`: a Pinia store `useFireUi` with `setLayer(name, on)` and `ensureLayer(name)` (they flip `fireStore.layers[name]` and start the fetch that `toggleFire` starts today) and, for T508, `dialog`, `openDialog(next)`, `closeDialog()`.
- Produces in the manifest: `panels: [{ id: 'fire-map', host: 'map', order: 20, component: FireMapPanel }]`; each layer's toggle gets `key` (`burnt`, `hotspots`, `zones`), `isOn: () => useFireStore().layers[key]` and `set: (on) => useFireUi().setLayer(key, on)`.
- Produces `FireMapPanel.vue` (prop `context`): the pill, the attribution line, the zones-failed note with its retry button and the focus-ring anchor with their present markup, classes and test ids; the watchers that hand `fireStore.hotspots`, `burntAreas` and active `zones` to `context.facade` (`immediate`, and `markFeedFailed` when a setter returns `false`); a `flush: 'sync'` watcher that applies `fireStore.layers` to `context.facade.setFireLayerVisible` (zones only for an admin); on mount the labels, the remembered layers, `refreshVisible()` and the zones retry of today's first `onMounted`; the focus overlay, added when `context.hostMap` becomes a map (a watcher with `immediate` and `flush: 'sync'`) and removed when it becomes `null` or on unmount, and `consumeFireFocus` driven by `fireStore.focusRequest` and `context.mapActive`; on unmount the timer is cleared. The facade functions work before the map is mounted, so everything else runs in the panel's own `onMounted`. `MapView.vue` keeps `firePopup`, the dialogs and the context menu until T508; `LEGACY_LAYER_NAMES`, `toggleFire`, `ensureLayer`, `firePill`, `fireDataLayerOn`, `focusRingEl` and their helpers are gone, and the places that called `ensureLayer` call `useFireUi().ensureLayer`.

- [ ] **Step 1: Read, then write the failing tests.** Read `MapView.fire.test.js`, `MapView.toggles.test.js`, `MapView.b52.test.js` and `MapView.b66.test.js` for every query on `.fire-pill`, `.fire-attribution`, `[data-layer]`, `[data-testid="fire-focus-ring"]` and on `hooks.layerVisible`, and keep each element and call. Tests in `FireMapPanel.test.js`, each `[T507]`, with a fake context (`facade` of spies, `hostMap: shallowRef(fakeMap)`, `mapKit` with a fake `Overlay` class and an identity `fromLonLat`): `layers remembered from the last session are shown on mount, zones only for an admin`; `a change of a layer flag reaches the map in the same tick`; `a feed the map cannot read is marked failed`; `the pill shows the feed time and the attribution line only while a data layer is on`; `a focus request centres the map and shows the ring for 8 s, and unmount removes the overlay`; `the toggle pair of the manifest flips the store flag`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/modules/fire/components/FireMapPanel.test.js`. Expected: FAIL (`Failed to resolve import "./FireMapPanel.vue"`).
- [ ] **Step 3: Move** the blocks. The CSS rules of the moved elements move with them unchanged.
- [ ] **Step 4: Run** the seven unedited `MapView` test files and the rest. Run: `cd bee-with-me\frontend; npm test -- src/modules src/views src/platform src/composables src/architecture.test.js; npm run build`. Expected: PASS and a clean build. A test of `MapView*.test.js` that would need an edit stops the task.
- [ ] **Step 5: Commit** `refactor(fire): T507 fire layer state, pill and focus ring are the fire module's map panel`.

dod:
- `cd bee-with-me\frontend; npm test -- src/modules src/views src/platform src/composables src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`

### Task 508: fire popup, "Report fire here" and the two dialogs

**risk:** normal
**owner:** frontend-designer
**Files:**
- Move (`git mv`): `components/FirePopup.vue` and its test, `components/FieldReportForm.vue` to `modules/fire/components/`
- Create: `frontend/src/modules/fire/components/FireMapPopup.vue`, `FireDialogs.vue`, `FireMapPopup.test.js`, `FireDialogs.test.js`
- Modify: `frontend/src/modules/fire/index.js` (`popups`, `contextMenu`, one more panel, the named export `useFireUi`)
- Modify: `frontend/src/views/MapView.vue` (template lines 117 to 156; script lines 333, 339 to 341, 505 to 507, 524 to 620, 634 to 650, 665 to 671)

**Interfaces:**
- Consumes: `MapPopupHost.vue`, `MapContextMenu.vue`, `collectPopups`, `collectContextMenu` (wave 1, unchanged); `useFireUi` (T507); `components/SuppressionZoneForm.vue` at its present path (it moves in T509).
- Constraint: as in T507, `FireMapPopup.vue` and `FireDialogs.vue` import no `ol` module; a coordinate conversion in the moved code (`toLonLat`, `fromLonLat`) goes through `context.mapKit`.
- Produces in the manifest: `popups: [{ id: 'fire', component: FireMapPopup, kinds: ['hotspot', 'burnt_area'] }]`; `contextMenu: [{ id: 'fire-report-here', order: 10, labelKey: 'fire.report.here', testId: 'report-fire-here', onSelect: ({ lonLat }) => useFireUi().openDialog({ kind: 'report', target: { latitude: lonLat[1], longitude: lonLat[0] } }) }]`; panel `{ id: 'fire-dialogs', host: 'map', order: 30, component: FireDialogs }`.
- Produces `FireMapPopup.vue` (props `selection`, `context`; emits `close`): it renders `FirePopup` with exactly today's props and listeners and owns `fireBusy`, `fireError`, `runPopupAction`, `syncPopup`, dismiss, extinguish and create-zone (which opens the zone dialog through `useFireUi`). `FireDialogs.vue` (prop `context`): the two forms with today's props, `dialogBusy`, `dialogError`, the sequence guard, `submitReport`, `submitZone`; when `ui.dialog` becomes non-null it calls `context.closeContextMenu()`.
- Produces in `MapView.vue`: `popups = collectPopups(MODULES)`, `menuItems = collectContextMenu(MODULES)`; the popup slot is `<component :is="popup.component" :selection="selection" :context="mapContext" @close="firePopup = null" />`; `reportFromRow(pos)` keeps its place in the tracker row and calls `useFireUi().openDialog(...)` imported from `modules/fire/index.js`, with the 24 h rule unchanged.

- [ ] **Step 1: Read, then write the failing tests.** Read the seven `MapView*.test.js` files for every query on the `FirePopup` stub (props and emitted events), `.fire-popup-anchor`, `[data-testid="report-fire-here"]`, `[data-testid="report-fire-row"]` and the two forms, and keep each. Tests, each `[T508]`: `FireMapPopup.test.js`: `passes kind, properties, lon-lat, admin flag, busy and error text to the popup`; `dismiss calls the store, closes on success and shows the error text on failure`; `a second action while one runs is ignored`; `create zone opens the zone dialog at the popup position`. `FireDialogs.test.js`: `a report dialog submits through the store and shows the hotspots layer`; `a stale answer of an earlier dialog does not close the present one`; `opening a dialog closes the context menu`. `modules/fire/index.test.js` (appended): `the popup, the menu item and the panels are manifest contributions and MapView has no legacy entry` (the text of `MapView.vue` has no `until step 2`).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/modules/fire`. Expected: FAIL (`Failed to resolve import "./FireMapPopup.vue"`).
- [ ] **Step 3: Move** the components and the logic; keep every `data-testid` and class.
- [ ] **Step 4: Run** the seven unedited `MapView` test files and the rest. Run: `cd bee-with-me\frontend; npm test -- src/modules src/views src/platform src/composables src/architecture.test.js; npm run build`. Expected: PASS and a clean build.
- [ ] **Step 5: Commit** `refactor(fire): T508 fire popup, context-menu item and dialogs are manifest contributions`.

dod:
- `cd bee-with-me\frontend; npm test -- src/modules src/views src/platform src/composables src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`

### Task 509: the zones section of the Settings page is contributed by fire

**risk:** normal
**owner:** frontend-designer
**Files:**
- Move (`git mv`): `components/SuppressionZoneForm.vue` to `modules/fire/components/`
- Create: `frontend/src/modules/fire/components/FireZonesSettings.vue`, `FireZonesSettings.test.js`
- Modify: `frontend/src/modules/fire/index.js` (one more panel), `modules/fire/components/FireDialogs.vue` (import path)
- Modify: `frontend/src/modules/settings/views/SettingsView.vue` (the zones block of the template and its script; imports at lines 229 to 233)

**Interfaces:**
- Consumes: `collectPanels(MODULES, 'settings')`, `PanelHost.vue` (T504).
- Produces: panel `{ id: 'fire-zones-settings', host: 'settings', order: 10, component: FireZonesSettings }`; `FireZonesSettings.vue` (prop `context` with `isAdmin`) holds the zones block of `SettingsView.vue` with its markup, classes, test ids, texts (still the `settings.*` keys) and behaviour; `SettingsView.vue` renders `<PanelHost :panels="settingsPanels" :context="{ isAdmin }" />` where the block was and imports nothing of fire. The re-export `lib/fireErrors.js` stays until step 5 like every old path, also when nothing imports it any more.

- [ ] **Step 1: Read, then write the failing tests.** Read `SettingsView.zones.test.js`, `SettingsView.b54.test.js`, `SettingsView.test.js` and `SettingsView.photo.test.js` and list every query on the zones block. If `SettingsView.vue` uses the fire store outside that block, stop and report. Tests in `FireZonesSettings.test.js`, each `[T509]`: `lists the zones with disabled ones and offers enable and disable`; `a stale zone shows the conflict text and reloads the list`; `a viewer sees no zone form`; and in `modules/fire/index.test.js`: `the settings module imports nothing of fire` (the text of every file under `modules/settings/` contains none of `stores/fire`, `fireErrors`, `SuppressionZoneForm`).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/modules/fire`. Expected: FAIL (`Failed to resolve import "./FireZonesSettings.vue"`).
- [ ] **Step 3: Move** the block and the form.
- [ ] **Step 4: Run** the four unedited `SettingsView` test files and the rest. Run: `cd bee-with-me\frontend; npm test -- src/modules src/views src/platform src/architecture.test.js; npm run build`. Expected: PASS and a clean build.
- [ ] **Step 5: Commit** `refactor(fire): T509 the suppression zones section of Settings is a fire panel`.

dod:
- `cd bee-with-me\frontend; npm test -- src/modules src/views src/platform src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`

### Task 510: fire live handlers come from the manifest

**risk:** normal
**owner:** implementer
**Files:**
- Modify: `frontend/src/modules/fire/index.js` (`liveHandlers`, `live`)
- Modify: `frontend/src/composables/legacyLive.js` (the fire entries leave; the file is created by T543 of the tracking plan)
- Modify: `frontend/src/composables/useWebSocket.test.js`, `useWebSocket.b66.test.js`, `useWebSocket.dispatch.test.js` (mock path, section 5)
- Create: `frontend/src/modules/fire/live.test.js`

**Interfaces:**
- Consumes: `collectLiveHandlers`, `collectLiveHooks` and the `live` manifest field of tracking T543.
- Produces in the manifest: `liveHandlers: { fire_data_updated: (msg) => useFireStore().applyFireDataUpdated(msg), fire_zones_updated: () => useFireStore().applyFireZonesUpdated(), fire_alert: (msg) => useFireStore().applyFireAlert(msg), fire_alert_repeat: (msg) => useFireStore().applyFireAlertRepeat(msg), fire_alert_updated: (msg) => useFireStore().applyFireAlertUpdated(msg) }`; `live: { onTick: () => Promise.allSettled([store.retryFailed(), store.fetchOpenAlerts()]), onReconnect: () => store.refreshVisible() }` with `store = useFireStore()` read inside each function.

- [ ] **Step 1: Write the failing tests** in `live.test.js`, each `[T510]`: `each of the five fire message types reaches its store action`; `a tick retries failed feeds and refetches the open alarms, and neither failure stops the other`; `a reconnect refreshes the visible layers`; `the legacy live list holds no fire entry`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/modules/fire/live.test.js`. Expected: FAIL (the manifest has no `fire_alert` handler).
- [ ] **Step 3: Implement**; edit the three mock paths.
- [ ] **Step 4: Run.** Run: `cd bee-with-me\frontend; npm test -- src/modules src/composables src/platform src/views src/architecture.test.js; npm run build`. Expected: PASS and a clean build.
- [ ] **Step 5: Commit** `refactor(fire): T510 fire live messages are handled by the fire manifest`.

dod:
- `cd bee-with-me\frontend; npm test -- src/modules src/composables src/platform src/views src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`
