# Vertical slices, step 3 without the gateway: the `tracking` and `sos` modules and the thin live payload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give positions and SOS their own modules on both sides (`backend/modules/tracking/`, `backend/modules/sos/`, `frontend/src/modules/tracking/`, `frontend/src/modules/sos/`), make every writer of `location_events`, `repeater_events` and `sos_alerts` go through `tracking.api` and `sos.api`, and take names, ranks, phones, photo paths and teams out of the `location_update` and `sos_alert` messages of the open live channel, without touching how a frame is decoded, de-duplicated or acknowledged.

**Architecture:** `routers/locations.py` splits along its tables into two HTTP modules; because one old module becomes two, the old path is an explicit shim that names what it passes on, not a `sys.modules` alias. The SQL of the writers moves statement by statement into the two modules' repositories and the callers keep their order of work, so the mocked-connection tests of phase 1 run unedited. `hardware_reader/reader.py` is the one file shared with the future `gateway` module: its three handler bodies become calls to the two APIs in a separate, detachable PR (the backend half of the thin payload, T547, needs it and waits with it); `parser.py` and `hid_reader.py` are not opened. The frontend gets a live dispatch that reads handlers from the manifests, two stores behind the old `useLocationsStore` facade, and then the thin payload: frontend first (tolerant of both shapes), backend second.

**Tech Stack:** Python 3.11+, FastAPI, asyncpg, import-linter, pytest; Vue 3, Pinia, OpenLayers 10, vitest. No new dependency.

**Spec:** [`docs/superpowers/specs/2026-10-31-vertical-slices-programme-design.md`](../specs/2026-10-31-vertical-slices-programme-design.md) sections 5 ("Step 3", "Phase 3" item 3), 6, 7, 9; `Architecture/application/modular-monolith.md` sections 3, 4, 5.1 (fast path and thin payload), 7, 9; ADR 7, 15, 17, 19; `Architecture/principles/architecture-principles.md` (BP-01, BP-02, DP-02 are the ones this plan can break). Template: [`2026-11-10-vs-step1-settings.md`](2026-11-10-vs-step1-settings.md) section 1; contribution contract: [`2026-11-10-vs-map-shell.md`](2026-11-10-vs-map-shell.md) section 1 and [`2026-11-10-vs-step2-fire.md`](2026-11-10-vs-step2-fire.md) section 1.2.

**Base:** `upstream/develop` at `7f874bc`. Execution branches: `feature/vs-2-<task>` off `develop`, one PR per task. Wave overview: [`2026-11-10-vs-wave2-overview.md`](2026-11-10-vs-wave2-overview.md).

## Global Constraints

- The decisions and rules of the fire plan's Global Constraints apply unchanged (base branch, kernel names, frozen files, old paths until step 5, no behaviour change, no WebSocket security work, auth by default, existing tests unedited except import and mock paths and the edits of section 5, allowlist lines only with approval, `frontend-designer` for `.vue` and `.css`, entry chunk base 167,61 kB stated before and after in every frontend PR). Tags: `T54x`.
- **No gateway in this wave.** `backend/hardware_reader/parser.py`, `hid_reader.py` and `backend/routers/hardware_reader.py` are not edited by any task. The duplicate filter, the order "mark seen, store, acknowledge" and the acknowledgement of an unknown device stay exactly as they are; the fix of R-06 that the spec assigns to step 3 belongs to the gateway step and is validated on real hardware there. `reader.py` is edited by one task only (T542), which changes no decode and no ACK line and carries the hardware note in its PR.
- The fast path stays direct: no queue, no dispatcher, no extra connection and no new `await` between the INSERT and its `pg_notify` (BP-01, BP-02, modular-monolith.md 5.1). Every API function takes the caller's connection and opens no transaction of its own.
- Freshness is judged on `received_at`; no task touches that rule or the values of `lib/freshness.js`.
- REST stays the source of truth and keeps its fields: `GET /api/locations/live` and `GET /api/locations/sos` still return names, ranks, photos, phones and teams to a logged-in user. Thin applies to the two messages of the open channel only. `fire_alert*` payloads are not touched.
- `lib/groups.js` stays in `src/lib/`; the tracking store imports it from there.
- The stores of `people`, `teams` and `devices` (T444) are **not** needed by this plan and are not planned here: the names on the map come from the `/live` read model the tracking store already holds (section 1.4).

## Review Focus

1. A frame that is stored must be broadcast, and a frame from an inactive person must be stored and not broadcast: the split of `_handle_bee` into API calls must keep both, in today's statement order (T542, the 13 unedited tests of `test_reader_handlers.py` plus `test_the_handlers_run_the_same_statements_in_the_same_order`).
2. An SOS must reach the banner with an id the Resolve button can post, even when the message carries no name and the follow-up request fails (T546, `a thin sos alert is shown at once and survives a failed refetch`).
3. A thin `location_update` for a device the browser has never seen must not draw an anonymous marker for 45 seconds: the store asks `/live` once, not once per frame (T546, `an unknown device triggers one refetch for a burst of frames`).
4. One old module, two new ones: a test that patched a name on `backend.routers.locations` would patch the shim's copy and test nothing (T540, `test_no_test_patches_a_name_of_the_locations_shim`).
5. Two stores behind one facade: resolving an SOS must clear the marker's flag, and the next frame that still asserts SOS on the device must not relight it or raise a second toast (T544, the unedited `stores/locations.test.js` plus `the sos hook is registered before the first live message`).

---

## 1. Design

### 1.1 What is shared between `tracking`, `sos` and `gateway`, and how it is cut

| File (lines on `7f874bc`) | `tracking` part | `sos` part | `gateway` part (stays) | Cut | Task |
|---------------------------|-----------------|------------|------------------------|-----|------|
| `backend/routers/locations.py` (143) | `/live`, `/trail`, `/{device_id}/history` | `/sos`, `/sos/{alert_id}/resolve` | none | two `http.py` files; the old path is a **named shim** (below) | T540 |
| `backend/hardware_reader/reader.py` (316, of which 56 are the dead serial `run()` inside a string) | last fix, previous SOS flag, `INSERT location_events`, the roster read, the payload and `pg_notify('location_update')`; `INSERT repeater_events` | `_ensure_sos_alert` (open-alert check, `INSERT sos_alerts`, the name read, `pg_notify('sos_alert')`), the "is an alert open" read | `status`, `_broadcast_status`, `_connect_kwargs`, `_port_and_baud`, `_device_row` (a read of `devices`), `_read_loop`, and the three handler names as orchestrators | the SQL goes to the two repositories; `_handle_bee`, `_ensure_sos_alert`, `_handle_repeater` keep name, signature and statement order and call the APIs | T542 |
| `backend/hardware_reader/hid_reader.py` (211), `parser.py` (162) | none | none | all of it | not opened; `hid_reader` imports `_handle_bee`, `_handle_repeater`, `_connect_kwargs` from `reader`, which keep their names | none |
| `backend/routers/test.py` (`record_position`, lines 56 to 150) and `backend/simulation.py:177-179` | the simulated INSERT, the roster read, the payload, the DELETE of the reset | the simulated alert INSERT, the DELETE of the reset | none (the spec lets `simulation` call the two APIs until it can feed `gateway`) | SQL to the repositories, order of work kept | T541 |
| `backend/routers/users.py:414-419`, `backend/routers/devices.py:208-210` | `UPDATE location_events SET user_id = NULL`; `DELETE location_events`, `DELETE repeater_events` | two `UPDATE sos_alerts`; `DELETE sos_alerts` | none | SQL to the repositories, called directly until the events of step 4 | T541 |
| `backend/main.py:45-63` (retention DELETE) | yes | none | none | stays in `main.py` (four tests call the loop there; `allowlist.json` says `until: 5`) | none |
| `backend/core/ws.py` (`FORWARDED_CHANNELS`) | `location_update` | `sos_alert` | `serial_status` is a direct broadcast, not a channel | not edited | none |
| `frontend/src/stores/locations.js` (200) | positions, trails, connection and snapshot state, `serialStatus` | alerts, toasts, the manual-resolve suppression | `serialStatus` moves to a gateway module later | two stores; the old path is a composite facade | T544 |
| `frontend/src/composables/useWebSocket.js` (115) | two handlers, two resync calls | one handler, one resync call | none | the socket stays; handlers and hooks are read from contributions | T543, T544 |

**Why not `import *` and why not an alias for `routers/locations.py`.** An alias makes the old name the new module; two modules cannot both be it. `import *` would copy every public name without saying which and would hide a missing one. The shim names each thing:

```python
"""Old import path of the tracking and sos HTTP modules, kept until step 5.

One old module became two, so this is not a sys.modules alias: it passes on the names below and nothing else.
A patch of a name here would hit this copy, not the module (test_no_test_patches_a_name_of_the_locations_shim).
"""
from fastapi import APIRouter

from ..modules.sos.http import open_sos_alerts, resolve_sos
from ..modules.sos.http import router as _sos_router
from ..modules.tracking.http import device_history, live_positions, location_trail, settings
from ..modules.tracking.http import router as _tracking_router

router = APIRouter()
router.include_router(_tracking_router)
router.include_router(_sos_router)
```

The tests use exactly these names and patch none of them (`git grep -noE "\blocations\.[A-Za-z_]+" -- backend/tests` gives `live_positions`, `location_trail`, `resolve_sos`, `router`).

### 1.2 Backend modules

| Module | Owns | Reads (read models) | Live message | Routes |
|--------|------|---------------------|--------------|--------|
| `tracking` | `location_events`, `repeater_events` | `devices`, `groups`, `sos_alerts`, `user_groups`, `users` | `location_update` | `GET /api/locations/live`, `/trail`, `/{device_id}/history` |
| `sos` | `sos_alerts` | `devices`, `users` | `sos_alert` | `GET /api/locations/sos`, `POST /api/locations/sos/{alert_id}/resolve` |

Both routers keep `prefix='/api/locations'` and `tags=['locations']`; no path of one matches a path of the other. `depends_on` stays empty: `devices` is not a module yet. `/live` joins `sos_alerts` for the effective SOS flag: that is a read model of `tracking`, declared in `reads_tables`, not a call to `sos`.

The repositories hold two INSERT statements for `location_events` (the reader's and the simulation's) and two for `sos_alerts`, each copied unchanged. They differ in columns and in the clock they store, tests read their arguments by position, and merging them is a behaviour question for the gateway step, where `simulation` is to feed `gateway` instead of writing at all.

### 1.3 Allowlist arithmetic on `7f874bc`

| Entries today | Count | What happens | Task |
|---------------|-------|--------------|------|
| `shims`: `backend.routers.locations` to `backend.config`, `backend.database`, `backend.json_columns` (`# until step 3`) | 3 | deleted | T540 |
| new in `module boundary: tracking` and `module boundary: sos`: the shim to each `http` (`# until step 5`) | +2 | added with approvals | T540 |
| `sql_writes`: `routers/test.py` (2), `routers/users.py` (2), `routers/devices.py` (3), `simulation.py` for `location_events` and `sos_alerts` (2) | 9 | deleted | T541 |
| new in `module_edges`: `backend.routers.users` and `backend.routers.devices` to `tracking.api` and to `sos.api` (`until: 4`, the reactions become events); `backend.routers.test` and `backend.simulation` to both (`until: 3`, `simulation` feeds `gateway` then) | +8 | added with approvals | T541 |
| `sql_writes`: `hardware_reader/reader.py` (3) | 3 | deleted (`gateway` to `tracking` and to `sos` are allowed edges: no `module_edges` row) | T542 |
| `shims`: `backend.hardware_reader.*` to `backend.config` and `backend.ws` (`# until step 3`) | 4 | **stay**: they go with the gateway step | none |

`completed_step` stays 2 after this plan: step 3 is complete only when `gateway` is a module.

### 1.4 Thin payload

| Message | Keys after T547 | Keys that leave |
|---------|-----------------|-----------------|
| `location_update` | `device_id`, `user_id`, `mgrs`, `latitude`, `longitude`, `altitude_m`, `speed_knots`, `course_deg`, `battery_voltage`, `gnss_satellites`, `gnss_valid`, `sos_active`, `repeater_mode`, `recorded_at`, `received_at` | `full_name`, `rank`, `photo_url`, `phone`, `groups` |
| `sos_alert` | `id`, `device_id`, `user_id`, `dev_sn`, `triggered_at` | `full_name`, `rank` |

modular-monolith.md 5.1 names the person key `person_id`; the column, the REST field and every consumer say `user_id`, and a rename is a second change of the contract, so the key stays `user_id` (section 6).

**Where the browser gets the names.** `applyLocationUpdate` already merges a message over the row it holds (`{ ...existing, ...data }`), and that row comes from `GET /api/locations/live`, which carries every joined field and is refetched every 45 seconds by the resync tick. A thin message therefore keeps the name, the photo and the teams of a known device with no code at all. Two cases need code (T546): a device the store does not hold, and a device whose `user_id` changed (reassigned); both ask `/live` once. Until the `people_changed` messages of step 4 exist, a rename or a new photo shows on the map after the next tick (at most 45 seconds) instead of with the next frame. That is the one behaviour difference of this plan; it is stated in the PR of T547.

The inactive-person rule stays: the frame is stored and not broadcast. The reader still reads `users.is_active` for that; the name read for the SOS message and the teams read go.

**Order of deployment.** T546 (frontend, handles both shapes) is merged and on bee-dev before T547 (backend) is merged. A browser tab that still runs the old frontend against the thin backend shows `SN:` instead of a name in the SOS toast until it is reloaded; nothing is lost.

### 1.5 Frontend modules

- **Live dispatch (T543).** `src/platform/live/dispatch.js` turns the manifests' `liveHandlers` and an optional manifest field `live: { setup?, onTick?, onReconnect? }` into what `useWebSocket.js` runs. `useWebSocket.js` keeps its path (seven `MapView` tests mock it there), its socket life cycle, its two timers and its three returned names. Handlers that have no module yet are legacy entries in `composables/legacyLive.js`, imported through the old store paths so the three `useWebSocket` tests keep mocking them.
- **Two stores, one facade (T544).** `modules/tracking/store.js` (`useTrackingStore`) and `modules/sos/store.js` (`useSosStore`); `sos` depends on `tracking` and reaches it through `modules/tracking/index.js`, which exports the store hook. `tracking` does not know `sos`: it offers `addUpdateHook(fn)` and `patchPosition(deviceId, fields)`. The sos store registers one hook that computes the effective SOS flag and raises the toast, and the sos manifest's `live.setup` creates the store before the first message. `stores/locations.js` stays as `useLocationsStore`, a store that returns the refs and actions of the two (the same 23 names), for `MapView.vue`, `DevicesView.vue`, `UsersView.vue` and 12 test files.
- **Libraries.** `lib/freshness.js`, `lib/photoMarker.js`, `lib/trackerTooltip.js` and their tests move to `modules/tracking/lib/`; re-exports stay at the old paths, because `useMap.js`, `MapView.vue` and four `useMap` tests import them there.
- **Banner and toast.** `SOSBanner.vue` becomes the sos manifest's banner (priority 10, statically imported: an alarm is not behind a chunk load). `SOSToast.vue` becomes a `map-root` panel (T545).
- **The tracker layer and its timer.** The tracker markers, the trail, the checkpoints, the tooltip and `staleTimer` (the 60 s restyle that lets a marker go stale without a new frame, BP-01) stay in the `useMap` facade for T540 to T547. `staleTimer` is `tracking`'s and moves only together with the tracker layer. `tickTimer` (`MapView.vue`, 10 s, the age labels of the tracker rows) is `tracking`'s and moves only together with the tracker panel. Both moves are planned as the last two tasks (T548, T549), explicitly and separately, each with its difference and risk; the wave closes without them if they are not approved (section 6, item 1).

## 2. File map and who else touches each file (as of `7f874bc`)

Commands used: `git grep -nE "hardware_reader|_handle_bee|_handle_repeater|_ensure_sos_alert|_device_row" -- backend tools`; `git grep -nE "location_events|sos_alerts|repeater_events" -- backend ":!backend/tests" ":!backend/db"`; `git grep -noE "\blocations\.[A-Za-z_]+" -- backend/tests`; `git grep -nE "from '[^']*(stores/locations|SOSBanner|SOSToast|useWebSocket|lib/freshness|lib/photoMarker|lib/trackerTooltip|lib/groups)" -- frontend/src`; `git grep -nE "vi\.mock\('[^']*(stores/locations|useWebSocket|freshness|photoMarker|trackerTooltip|SOS)" -- frontend/src`.

| File | This plan | Also read or written by |
|------|-----------|-------------------------|
| `backend/routers/locations.py` | T540: becomes the shim | `conftest.py:17,29`; `test_locations_api.py`, `test_locations_db.py`, `test_sos_api.py`, `test_b50.py`, `test_b72.py` call its functions |
| `backend/main.py`, `backend/modules/registry.py`, `importlinter.toml`, `approved_additions.py`, `allowlist.json` (hot) | T540 (router line, two registry lines, contracts), T541, T542 (rows) | fire T502, T503; weather T520 |
| `backend/routers/users.py`, `backend/routers/devices.py` | T541 (the statements of section 1.1) | fire T503 (their fire imports; `devices.py:206-239` is edited by both: T541 after T503) |
| `backend/routers/test.py`, `backend/simulation.py` | T541, T547 (payload) | `test_api_simulate.py`, `test_simulation.py`; smoke step e |
| `backend/hardware_reader/reader.py` | T542 only | `hid_reader.py:19`; `test_reader_handlers.py`, `test_hid_process_frame.py`, `test_hid_run.py`, `test_migration_0006.py`, `test_b86_password_not_logged.py`, `test_b93_lifespan_shutdown.py` |
| `tools/smoke.py`, `backend/tests/test_smoke_script.py`, `docs/SMOKE.md` | T540 adds step j | fire T502 (h), weather T520 (i) |
| `frontend/src/composables/useWebSocket.js` (hot) | T543, T544 | fire T510; three tests of its own, seven `MapView` tests mock it |
| `frontend/src/platform/manifest.js` | T543 (`live`) | fire T504 (`panels`, `toggle`) |
| `frontend/src/stores/locations.js` | T544: becomes the facade | `MapView.vue:320`, `DevicesView.vue:74`, `UsersView.vue:208`, `SOSBanner.vue`, `SOSToast.vue`, 12 test files |
| `frontend/src/modules/index.js`, `frontend/src/i18n/en.js`, `bg.js` (hot) | T544 (two lines; the `sos` namespace) | fire T505, weather T521 |
| `frontend/src/components/legacyBanners.js`, `AppLayout.vue`, `platform/map-shell/BannerStack.test.js` | T544 (the SOS line; the file goes when it is empty) | fire T505 |
| `frontend/src/views/MapView.vue` (hot) | T545, T548 | fire T504, T506 to T508; weather T522; overview T580 |
| `frontend/src/composables/useMap.js` (hot) | T549 | fire T506; overview T580 |

## 3. Task order, PRs, reviewers, parallel work

| PR | Task | Content | Needs | Owner | Reviewers |
|----|------|---------|-------|-------|-----------|
| 1 | T540 | backend `tracking` and `sos`: HTTP side | fire T500, T501 | implementer | breaker + security-reviewer (`routers/**`, `main.py`) |
| 2 | T541 | `tracking.api`, `sos.api` and the callers outside the hardware reader | T540, fire T503 (same block of `devices.py`) | implementer | breaker + security-reviewer (`routers/**`) |
| 3 | T542 | `reader.py` handlers call the APIs (detachable) | T541 | implementer | breaker + security-reviewer (`hardware_reader/**`); hardware note |
| 4 | T543 | frontend live dispatch | nothing | implementer | breaker |
| 5 | T544 | frontend `tracking` and `sos`, part 1 (stores, libraries, banner, texts, live handlers) | T543, fire T505 and T510 (assembly and live chains) | frontend-designer | breaker |
| 6 | T545 | SOS toast as a panel | T544, fire T504, its turn in the map chain | frontend-designer | breaker |
| 7 | T546 | frontend tolerates the thin payload | T544 | implementer | breaker |
| 8 | T547 | backend sends the thin payload (detachable together with T542) | T542, T546 merged and deployed to bee-dev | implementer | breaker + security-reviewer (`routers/**`, the live channel) |
| 9 | T548 | tracker panel becomes a tracking panel (explicit, optional) | T545, fire T508 | frontend-designer | breaker |
| 10 | T549 | tracker layers become the tracking map entry (explicit, optional) | T548 or T545, fire T506 | frontend-designer | breaker |

**Inside the plan.** Backend (T540, T541, T542, T547) and frontend (T543 to T546) run at the same time; the only cross dependency is T547 after T546. **T547 needs T542.** Real frames reach the live channel only through `reader.py`, and `routers/test.py` sends no `sos_alert` at all, so a thin payload on the simulation path alone would protect nothing and would leave two payload shapes in the tests. Both tasks also edit `tracking/api.py`, `sos/api.py` and `reader.py`. If T542 is held back for hardware validation, T547 waits with it: the wave then closes with the full payloads and with the tolerant frontend of T546 already merged, and R-22 stays open until both are in.

**PR gate (every PR):** the gate of the fire plan, section 3. Additions: T540 to T542 and T547 paste the PASS line of smoke step e (`simulated frame reaches /ws`), which is the only end-to-end check of the fast path; T547 also adds to its PR body the two payloads copied from a `/ws` session in the dev stack. T542 carries this note in its PR body: "Hardware path: `parser.py` and `hid_reader.py` are unchanged byte for byte; in `reader.py` three handler bodies now call `tracking.api` and `sos.api`, which run the same statements in the same order on the same connection; decode, duplicate filter and ACK are untouched. Not run against a real gateway by the agent. The owner and the device maker decide whether it is validated on hardware before or after the merge." No `ef-migration-reviewer` (no migration).

## 4. Risks, rollback, not verified

| Risk | Mitigation |
|------|------------|
| A moved statement changes its text, its argument order or the connection method, and a mocked test passes while the real database fails | every statement is copied unchanged; the `db`-marked tests (`test_locations_db.py`, `test_devices_db.py`, `test_users_db.py`, `test_simulation.py`, `test_migration_0006.py`) run in CI on PostGIS; smoke step e runs the simulated frame against a real database before every PR |
| T542 is held back for hardware validation | the wave closes without it and without T547: three `sql_writes` rows stay (`until: 3`, not overdue), both paths keep the full payload, the frontend of T546 handles both shapes, and R-22 is reported as open by T590 |
| A refetch of `/live` that started before a new device's first frame lands after it and wipes the marker (`fetchLive` replaces the whole map; the thin payload asks for a refetch per new device) | T546 makes `fetchLive` keep a row that a live message updated after the request started |
| The `locations` routes move from the fifth place of the route table to the module list | no path overlaps; only the tag order in `/docs` changes; stated in the PR body |
| The facade store returns refs of two other stores and a consumer assigns to one (`store.sosAlerts = [...]` in tests) | Pinia unwraps the shared ref, so the assignment reaches the owning store; `stores/locations.test.js`, the two `SOSBanner` tests and seven `MapView` tests are the proof, unedited. Fallback if it does not hold: `sos` state stays in one store file with tracking for this wave and the split waits for step 5; stop and report |
| Handlers run through one more function per message | a `Map` lookup and a short array; no reactive state on the path; an error in one handler is logged and does not stop the next (today it would throw out of `onmessage`) |
| Thin payload: a name changed in the Users page shows up to 45 s later on the map | stated; removed by the `people_changed` message of step 4 |
| Thin payload: a consumer outside this repo reads `full_name` from `/ws` | none is known; the device maker is asked (section 6, item 3) before T547 is merged |
| bee-dev gets a broken image | smoke gate before every PR; `git revert -m 1 <merge>` |

**Rollback.** No schema or data change. Revert newest first: T547 alone (the frontend keeps working with the full payload); then T542 (never while T547 is merged); T541 then T540; frontend T549, T548, T545, T546, T544, T543. T546 must not be reverted while T547 is merged.

**Not verified while planning:**
- That the payload built in `routers/test.py:120-150` has exactly the 20 keys of the reader's payload (the plan read the first nine lines of it): T541 step 1 compares them and reports a difference instead of unifying it.
- Checked while the plan was reviewed: `routers/test.py` writes `sos_alerts` (line 92) and sends only `pg_notify('location_update', ...)` (line 141), never a `sos_alert` message. The thin `sos_alert` is therefore tested through `reader._handle_bee` (T547).
- What `tools/smoke.py` step e asserts about the message body: T547 step 1.
- That a Pinia setup store can return refs taken with `storeToRefs` from another store and stay writable through the facade: T544 step 4 (fallback above).
- No frame was sent by real hardware and no browser was opened while planning.

## 5. Existing tests

All existing tests stay green without edits, except:

| File | Edit | Kind | Task |
|------|------|------|------|
| `backend/tests/architecture/test_sql_ownership.py:55-58`, `test_import_contracts.py:196`, `module_map.py` | path strings of the moved SQL, if a test names one | file path | T540 to T542 |
| `backend/tests/modules/gateway/test_reader_handlers.py:24-29` | `LOCATION_KEYS` loses `full_name`, `rank`, `photo_url`, `phone`, `groups`; `SOS_KEYS` loses `full_name`, `rank`; an assertion that reads one of those values from a payload is deleted | deliberate: the test pins the payload this step changes; the reader builds its payload through the two APIs by then, because T542 is merged first | T547 |
| `backend/tests/test_api_simulate.py`, `backend/tests/test_simulation.py` | the same, where a test reads a name from the simulated message | deliberate | T547 |
| the frontend test files that move with their code (`lib/freshness.test.js`, `lib/trackerTooltip*.test.js`, `SOSBanner*.test.js`) | relative import and `vi.mock` paths | import path | T544 |
| `frontend/src/composables/useWebSocket.test.js`, `useWebSocket.b66.test.js`, `useWebSocket.dispatch.test.js` | `vi.mock('../stores/locations', ...)` becomes two mocks, of `../modules/tracking/store.js` and `../modules/sos/store.js`, and the fake `loc` is split into the two fakes with the same spies; no assertion changes. No mock of `../stores/locations` is left in the three files, because `useWebSocket.js` no longer imports the facade (T544) | mock path and the shape of the fake | T544 |
| `frontend/src/platform/map-shell/BannerStack.test.js` | fire T505 already moved the two cases at lines 34 to 42 to an inline fixture list; here the import of `legacyBanners.js` and any other use of `LEGACY_BANNERS` in the file go with the deleted file (an AppLayout case that passed the legacy list passes nothing); the real order is asserted in `src/modules/sos/index.test.js` against the module list | deliberate: the file it imported is gone | T544 |

`backend/tests/conftest.py`, `test_locations_api.py`, `test_locations_db.py`, `test_sos_api.py`, `test_b50.py`, `test_b72.py`, `test_hid_process_frame.py`, `test_hid_run.py`, `test_migration_0006.py` and `frontend/src/stores/locations.test.js` are not edited.

## 6. Open to the owner, the device maker and hand-offs

1. **To the maintainer: the tracker panel and the tracker layers (T548, T549).** The decision of wave 1 keeps them in the facade. They are planned as explicit, separate, last tasks; say whether they run in this wave or wait for the gateway step.
2. **To the owner and the device maker: T542.** It edits `hardware_reader/reader.py` without changing decode, duplicate filter or ACK. Is a run against the real gateway wanted before the merge, who does it and when (spec section 9, question 2)? If the answer is "not before the gateway step", T542 waits and T547 (the thin payload on the backend) waits with it; nothing else in the wave depends on either.
3. **To the device maker: the thin payload.** Does anything on the device side, the gateway side or a second client read `full_name`, `rank`, `phone`, `photo_url` or `groups` from `location_update`, or `full_name` and `rank` from `sos_alert`? T547 is not merged before this is answered and before T542 is merged.
4. **To the architecture owner (text proposals, not edited here):** modular-monolith.md 5.1 (`user_id` instead of `person_id`; the browser joins names from the `/live` read model until the stores and `..._changed` messages of step 4); 4.2 (`simulation` calling `tracking.api` and `sos.api` until the gateway step, as the spec allows); 7 (the `live` field of the frontend manifest); `Architecture/application/api-contracts.md` (the two message shapes).
5. **Hardware path fix (R-06, ES-23).** Not in this wave. The three expected-to-fail tests of phase 1 that pin "ACK after store" stay expected-to-fail.
6. **Retention** of `location_events` stays in `main.py` (fire plan, section 6, item 4).

---

### Task 540: backend `tracking` and `sos` modules, the HTTP side

**risk:** security
**owner:** implementer
**Files:**
- Create: `backend/modules/tracking/{__init__.py, module.py, api.py, http.py, infrastructure/__init__.py, infrastructure/repository.py}` and the same six for `backend/modules/sos/`
- Modify: `backend/routers/locations.py` (becomes the shim of section 1.1)
- Modify: `backend/modules/registry.py` (two imports, two names), `backend/main.py` (the name `locations` leaves line 19; line 269 is deleted)
- Modify: `backend/tests/architecture/importlinter.toml`, `approved_additions.py`
- Modify: `tools/smoke.py`, `backend/tests/test_smoke_script.py`, `docs/SMOKE.md` (step j)
- Create: `backend/tests/modules/tracking/test_tracking_module.py`, `backend/tests/modules/sos/test_sos_module.py`

**Interfaces:**
- Consumes: the loader (fire T500), the direction ratchet (fire T501), `backend.auth.get_current_user`, `backend.core.database.get_conn`, `backend.core.config.settings`, `backend.core.json_columns.decode_json_columns`.
- Produces `tracking/infrastructure/repository.py`: `async fetch_live(conn, max_age_hours) -> list[Record]`, `async fetch_trail(conn, minutes) -> list[Record]`, `async fetch_history(conn, device_id, from_dt, to_dt, limit, offset) -> list[Record]`; `sos/infrastructure/repository.py`: `async fetch_open_alerts(conn) -> list[Record]`, `async resolve_alert(conn, alert_id, user_id, notes) -> None`. The five SQL texts, their parameter order and the connection method (`fetch` four times, `execute` for the resolve) are copied unchanged.
- Produces `tracking/http.py`: `router = APIRouter(prefix='/api/locations', tags=['locations'])`, the module attribute `settings`, and `live_positions`, `location_trail`, `device_history` with today's signatures, defaults and return shapes. `sos/http.py`: the same router arguments, `open_sos_alerts`, `resolve_sos`.
- Produces the manifests of section 1.2 (`api.py` of both is a docstring in this task) and the registry line `MODULES = (fire_manifest, settings_manifest, tracking_manifest, sos_manifest)` (other modules keep their place if they were merged first).
- Produces in `importlinter.toml`: the three `shims` lines of section 1.3 are gone; contracts `boundary-tracking` and `boundary-sos` (`type = "forbidden"`, `source_modules` = `rules.LEGACY_SOURCES` plus every other `backend.modules.<name>` on disk, `forbidden_modules` = `http`, `infrastructure`, `module` of the module, `allow_indirect_imports = true`, `ignore_imports` with the shim edge to the module's `http`, `# until step 5`, each with an approval); both names appended to the `source_modules` of every other `module boundary:` contract.
- Produces in `tools/smoke.py`: step `'j. GET /api/locations/sos = 200'`, `needs=('c. admin login + token refresh',)`; `s_sos` expects 200 and a JSON list.

- [ ] **Step 1: Write the failing tests**, tagged `T540`. `test_tracking_module.py`: `test_manifest` (name, the two owned tables, the five read tables, `live_messages == ('location_update',)`, `manifest.router is http.router`, no public route); `test_the_shim_passes_on_the_module_functions` (`backend.routers.locations.live_positions is backend.modules.tracking.http.live_positions`, likewise `location_trail`, `device_history`, `settings`, and for sos `open_sos_alerts`, `resolve_sos`); `test_the_shim_router_serves_the_five_routes` (the `(path, methods)` pairs of `backend.routers.locations.router.routes` are the five of today); `test_no_test_patches_a_name_of_the_locations_shim` (no file under `backend/tests` other than this test file contains `setattr(locations` or `'backend.routers.locations.`; the two needles are built by concatenation in the test, so it does not match itself); `test_the_five_routes_are_served_once_by_the_real_app`; `test_every_route_needs_a_login` (401 without a token for all five on `backend.main.app`); `test_openapi_operation_ids_are_unchanged` (a literal list generated on `develop` before the move); `test_main_no_longer_mounts_the_locations_router`; `test_live_reads_the_freshness_horizon_from_the_settings` (`monkeypatch.setattr(settings, 'live_position_max_age_hours', 7)`: the mocked `conn.fetch` got `7` as its argument). `test_sos_module.py`: `test_manifest` (name, `owns_tables == ('sos_alerts',)`, `live_messages == ('sos_alert',)`); `test_resolve_runs_the_same_statement` (the mocked `conn.execute` got a text containing `UPDATE sos_alerts`, then the alert id, the user id and the notes). In `test_smoke_script.py`: `test_sos_step_passes_on_200_with_a_list` and `test_sos_step_fails_on_500`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\tracking\test_tracking_module.py backend\tests\modules\sos\test_sos_module.py -q`. Expected: FAIL with `ModuleNotFoundError: No module named 'backend.modules.tracking'`.
- [ ] **Step 3: Split** the file into the two modules (`git mv backend/routers/locations.py backend/modules/tracking/http.py`, then cut the two sos endpoints into `sos/http.py` and the SQL into the repositories), write the shim, the manifests, the registry lines, the two `main.py` edits and the smoke step.
- [ ] **Step 4: Extend, then shrink the allowlist** (contracts, two shim lines, approvals, `source_modules`; then `regen.py --remove-stale`). Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\architecture -q`. Expected: PASS, including `test_every_contract_bites` for both new contracts and `test_real_module_edges_match_the_allowlist_exactly` (the shim's two imports are inside its owners).
- [ ] **Step 5: Run** the module tests and the unedited API tests. Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_b50.py backend\tests\test_b72.py backend\tests\test_smoke_script.py backend\tests\test_b49.py backend\tests\test_startup_migrations.py -q`. Expected: PASS.
- [ ] **Step 6: Commit** `refactor(tracking): T540 tracking and sos become backend modules behind the locations shim`. PR body: the shim and why it is not an alias, the new place of the routes, the allowlist arithmetic (3 deleted, 2 added).

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_b50.py backend\tests\test_b72.py backend\tests\test_smoke_script.py backend\tests\test_b49.py backend\tests\test_startup_migrations.py -q`

### Task 541: `tracking.api` and `sos.api`, and the writers outside the hardware reader

**risk:** security
**owner:** implementer
**Files:**
- Modify: `backend/modules/tracking/api.py`, `infrastructure/repository.py`; create `backend/modules/tracking/domain/__init__.py`, `domain/payload.py`
- Modify: `backend/modules/sos/api.py`, `infrastructure/repository.py`
- Modify: `backend/routers/test.py:56-150`, `backend/simulation.py:175-180`, `backend/routers/users.py:414-419`, `backend/routers/devices.py:208-210`
- Modify: `backend/tests/architecture/allowlist.json`, `approved_additions.py`, `importlinter.toml` (`domain` joins the `forbidden_modules` of `boundary-tracking`)
- Create: `backend/tests/modules/tracking/test_tracking_api.py`, `backend/tests/modules/sos/test_sos_api_commands.py`

**Interfaces:**
- Consumes: T540; the present statements of the four callers.
- Produces `tracking/domain/payload.py` (pure): `location_update_payload(*, device_id, user_id, roster, groups, mgrs, latitude, longitude, altitude_m, speed_knots, course_deg, battery_voltage, gnss_satellites, gnss_valid, sos_active, repeater_mode, recorded_at, received_at) -> dict` with today's 20 keys in today's order (`roster` is the `users` row or `None`; `recorded_at` and `received_at` are `datetime` and are written with `isoformat()`).
- Produces `tracking/api.py` (each function passes its arguments to the repository function of the same name, looked up at call time, on the caller's connection):
  - `async insert_simulated_position(conn, *, device_id, user_id, msg_id, at, latitude, longitude, mgrs, altitude_m, speed_knots, gnss_satellites, battery_voltage, sos_active, gnss_valid) -> Record` (the INSERT of `routers/test.py`, `RETURNING id`)
  - `async person_of(conn, user_id) -> Record | None` (the `users` read) and `async groups_of(conn, user_id) -> list[dict]` (the teams read): two functions, because the reader returns for an inactive person between the two reads and must not run the second one
  - `async publish_position(conn, payload: dict) -> None` (`SELECT pg_notify('location_update', $1)` with `json.dumps(payload)`)
  - `location_update_payload` (re-exported from the domain)
  - `async forget_person(conn, user_id) -> None`, `async delete_device_positions(conn, device_id) -> None`, `async delete_device_heartbeats(conn, device_id) -> None`, `async delete_positions_of_devices(conn, device_ids) -> int`
- Produces `sos/api.py`: `async open_simulated_alert(conn, device_id, user_id, at) -> None` (the `INSERT ... WHERE NOT EXISTS` of `routers/test.py`), `async forget_person(conn, user_id) -> None` (the two UPDATEs, `user_id` first), `async delete_device_alerts(conn, device_id) -> None`, `async delete_alerts_of_devices(conn, device_ids) -> int`.
- Produces in the callers: the same order of work with the SQL replaced by these calls. `devices.py`: `sos_api.delete_device_alerts`, `tracking_api.delete_device_positions`, `tracking_api.delete_device_heartbeats`, in that order, before the fire lock of fire T503. `routers/test.py`: `record_position` keeps its name, signature, return value and the 400 for an inactive person.
- Produces in `allowlist.json`: the 9 `sql_writes` rows of section 1.3 are gone; 8 `module_edges` rows with approvals (reason for the `until: 4` rows: "deleting or deactivating a person or a device clears positions and alerts directly until the PersonDeleted and DeviceDeleted events of step 4"; for the `until: 3` rows: "the simulation writes through the two APIs until it can feed the gateway module").

- [ ] **Step 1: Read, then write the failing tests.** Read `routers/test.py:56-150` to the end and write into the PR body whether its payload has the reader's 20 keys (it sends no `sos_alert` message, only the INSERT at line 92); a difference is kept, not unified. Tests, tagged `T541`. `test_tracking_api.py`: `test_payload_has_todays_keys_in_todays_order` (the 20 names as a literal list; `roster=None` gives `None` for the four personal fields); `test_api_looks_the_implementation_up_at_call_time` (parametrised over the repository-backed names); `test_each_command_runs_on_the_callers_connection_without_a_transaction` (a mocked connection: `conn.transaction` is never called); `test_publish_sends_one_notify_on_the_location_channel` (the text contains `pg_notify('location_update'`); `test_deleting_a_device_keeps_the_order_alerts_positions_heartbeats` (through `DELETE /api/devices/{id}/permanent` with the mocked connection). `test_sos_api_commands.py`: `test_forget_person_clears_user_id_then_resolved_by`; `test_a_simulated_alert_is_not_opened_twice` (the statement text contains `WHERE NOT EXISTS`). In both: `test_no_writer_outside_the_modules_is_left` (`sql_scan.scan_writes` over `backend/` finds `location_events`, `repeater_events` and `sos_alerts` writes only in the two repositories, `hardware_reader/reader.py` and `main.py`).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\tracking\test_tracking_api.py backend\tests\modules\sos\test_sos_api_commands.py -q`. Expected: FAIL with `AttributeError: module 'backend.modules.tracking.api' has no attribute 'location_update_payload'`.
- [ ] **Step 3: Move** the statements and switch the four callers.
- [ ] **Step 4: Shrink and carry the allowlists** (9 rows deleted by hand, 8 rows and approvals added). Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\architecture -q`. Expected: PASS.
- [ ] **Step 5: Run** the DoD list. Expected: PASS, with `test_api_simulate.py`, `test_users_api.py`, `test_devices_api.py` and `test_api_fire_alerts.py` unedited.
- [ ] **Step 6: Commit** `refactor(tracking): T541 positions and alerts are written through tracking.api and sos.api`.

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_api_simulate.py backend\tests\test_api_users.py backend\tests\test_api_devices.py backend\tests\test_api_fire_alerts.py backend\tests\test_b47.py backend\tests\test_simulation.py -q`

### Task 542: the reader's handlers call `tracking.api` and `sos.api` (detachable, hardware note)

**risk:** security
**owner:** implementer
**Files:**
- Modify: `backend/hardware_reader/reader.py` (imports; the bodies of `_handle_bee`, `_ensure_sos_alert`, `_handle_repeater`, lines 66 to 237; nothing else)
- Modify: `backend/modules/tracking/api.py`, `infrastructure/repository.py`; `backend/modules/sos/api.py`, `infrastructure/repository.py`
- Modify: `backend/tests/architecture/allowlist.json` (3 rows)
- Create: `backend/tests/modules/gateway/test_reader_delegates.py`

**Interfaces:**
- Consumes: T541 (`person_of`, `groups_of`, `publish_position`, `location_update_payload`).
- Produces `tracking/api.py`: `async last_fix(conn, device_id) -> Record | None`, `async previous_sos_flag(conn, device_id) -> bool | None`, `async insert_position(conn, *, device_id, user_id, msg_id, recorded_at, received_at, latitude, longitude, mgrs, altitude_m, speed_knots, course_deg, gnss_satellites, battery_voltage, sos_active, repeater_mode, raw_flags, gnss_valid) -> None`, `async insert_heartbeat(conn, device_id, msg_id, battery_voltage) -> None`. `sos/api.py`: `async has_open_alert(conn, device_id) -> bool`, `async raise_sos(conn, *, device_id, user_id, dev_sn, triggered_at) -> bool` (the body of `_ensure_sos_alert`: the open-alert check, the INSERT, the name read, the notify with today's seven keys; `True` when it opened one). Every statement is the reader's, unchanged.
- Produces in `reader.py`: `from ..modules.sos import api as sos_api` and `from ..modules.tracking import api as tracking_api`; `_handle_bee(frame, conn)` keeps its checks, log lines and order: device row; when there is no fix `tracking_api.last_fix` (and the same INFO line and return when there is none); `tracking_api.previous_sos_flag`; `received_at = datetime.now(timezone.utc)`; `tracking_api.insert_position`; `_ensure_sos_alert` on a rising edge; `sos_api.has_open_alert`; `tracking_api.person_of`, the return for an inactive person, then `tracking_api.groups_of` (so an inactive person still causes no teams read); `tracking_api.publish_position(conn, tracking_api.location_update_payload(...))`. `_ensure_sos_alert(frame, device, conn)` calls `sos_api.raise_sos` and logs `'SOS ALERT opened for dev_sn=%s'` when it returns `True`. `_handle_repeater` keeps its device check and calls `tracking_api.insert_heartbeat`. `_device_row`, `status`, `_read_loop`, `_connect_kwargs`, `_port_and_baud`, `_broadcast_status` and the string that holds the old serial `run()` are not touched.

- [ ] **Step 1: Pin, then write the failing tests.** First record what the unchanged code does: a helper in `test_reader_delegates.py` runs `_handle_bee` and `_handle_repeater` against the mocked connection of `gateway_fakes.py` for six frames (fix, no fix with a previous fix, no fix without one, rising SOS, a fix from a device whose person is inactive, repeater heartbeat) and returns the list of `(method, sql text, args)`; write the six lists as literals from a run on `develop`. The inactive-person list ends with the `users` read: no `user_groups` statement and no `pg_notify`. Tests, tagged `T542`: `test_the_handlers_run_the_same_statements_in_the_same_order` (parametrised over the six frames: the recorded list equals the literal); `test_reader_holds_no_sql_for_positions_or_alerts` (the text of `reader.py` outside the trailing string contains none of `INSERT INTO`, `location_events`, `sos_alerts`, `repeater_events`, `pg_notify`); `test_hid_reader_still_binds_the_reader_handlers` (`hid_reader._handle_bee is reader._handle_bee`, likewise `_handle_repeater`, `_connect_kwargs`).
- [ ] **Step 2: Run.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\gateway\test_reader_delegates.py -q`. Expected: `test_the_handlers_run_the_same_statements_in_the_same_order` PASSES on the unchanged code (it is the pin) and `test_reader_holds_no_sql_for_positions_or_alerts` FAILS.
- [ ] **Step 3: Implement** the six API functions and the three handler bodies.
- [ ] **Step 4: Run** the gateway tests unedited, the architecture tests (delete the three `sql_writes` rows of `hardware_reader/reader.py`; no `module_edges` row is needed, `gateway` may call both) and the rest. Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_parser.py backend\tests\test_migration_0006.py backend\tests\test_b93_lifespan_shutdown.py -q`. Expected: PASS.
- [ ] **Step 5: Gate check, not a test** (a permanent test would compare `develop` with itself after the merge and would fail for good when the gateway step edits the parser). Run: `cd bee-with-me; git fetch upstream; git diff --stat upstream/develop...HEAD -- backend/hardware_reader/parser.py backend/hardware_reader/hid_reader.py backend/routers/hardware_reader.py`. Expected: no output. Paste the command and its empty output into the PR body.
- [ ] **Step 6: Commit** `refactor(gateway): T542 the reader stores positions and SOS through tracking.api and sos.api`. PR body: the hardware note of section 3 word for word.

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_parser.py backend\tests\test_migration_0006.py backend\tests\test_b93_lifespan_shutdown.py -q`

### Task 543: frontend live dispatch from contributions

**risk:** normal
**owner:** implementer
**Files:**
- Create: `frontend/src/platform/live/dispatch.js`, `frontend/src/platform/live/dispatch.test.js`, `frontend/src/composables/legacyLive.js`
- Modify: `frontend/src/platform/manifest.js` (optional field `live`), `frontend/src/platform/manifest.test.js` (one test appended)
- Modify: `frontend/src/composables/useWebSocket.js` (`resync`, `onopen`, `onmessage`)

**Interfaces:**
- Consumes: the manifests' `liveHandlers` (required field since T306, empty everywhere today).
- Produces `dispatch.js` (pure, imports nothing): `collectLiveHandlers(modules, legacy = []) -> Map<string, Function[]>` (manifest handlers in list order, then legacy items `{ type, handler }`); `collectLiveHooks(modules, legacy = {}) -> { setup: Function[], onTick: Function[], onReconnect: Function[] }` (from each manifest's `live`, then `legacy.setup`, `legacy.onTick`, `legacy.onReconnect`); `dispatchLive(handlers, msg) -> void` (every handler of `msg.type` runs; a throw or a rejected promise is logged as `console.error('live handler <type> failed', error)` and the next one runs; an unknown type does nothing); `runHooks(list) -> Promise<void>` (all of them, none stops another, a rejection is swallowed as today's `.catch(() => {})` does).
- Produces in `manifest.js`: when `live` is present it is an object whose keys are among `setup`, `onTick`, `onReconnect` and whose values are functions.
- Produces `legacyLive.js`: `LEGACY_LIVE = { handlers: [...], hooks: { onTick: [...], onReconnect: [...] } }` with the eight handlers and the calls of today's `resync` and `onopen`, reaching the stores through `../stores/locations` and `../stores/fire` and each marked `// until step 2` or `// until step 3`. The three calls `fetchLive`, `fetchSOS`, `fetchTrail` stay one `onTick` entry (`Promise.all`), as today.
- Produces in `useWebSocket.js`: `resync()` is `runHooks(hooks.onTick)`; a reopen runs `resync()` and `runHooks(hooks.onReconnect)`; `onmessage` is `dispatchLive(handlers, JSON.parse(event.data))`; the `setup` hooks run once, on the first `connect()` of the page. `connect`, `disconnect`, `resync`, both timers, `catchUp` and the `stopped` and `isUnmounted` rules are unchanged.

- [ ] **Step 1: Write the failing tests** in `dispatch.test.js`, each `[T543]`: `handlers of one type run in manifest order, then legacy`; `a handler that throws is logged and the next one runs`; `a handler whose promise rejects is logged`; `an unknown type calls nobody`; `hooks are collected per kind and a failing hook does not stop the others`; `setup hooks are collected in list order`. In `manifest.test.js`: `validateManifest accepts a live field and names a malformed one` (`live: { onTick: 1 }`, `live: { later: () => {} }`).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/platform/live`. Expected: FAIL (`Failed to resolve import "./dispatch.js"`).
- [ ] **Step 3: Implement** the dispatch, the legacy list and the three edits of `useWebSocket.js`.
- [ ] **Step 4: Run** the three unedited `useWebSocket` tests first, then the rest. Run: `cd bee-with-me\frontend; npm test -- src/composables src/platform src/views src/modules src/architecture.test.js; npm run build`. Expected: PASS and a clean build.
- [ ] **Step 5: Commit** `refactor(live): T543 live messages are dispatched to handlers from contributions`.

dod:
- `cd bee-with-me\frontend; npm test -- src/composables src/platform src/views src/modules src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`

### Task 544: frontend `tracking` and `sos` modules, part 1 (stores, libraries, banner, texts, live handlers)

**risk:** normal
**owner:** frontend-designer
**Files:**
- Create: `frontend/src/modules/tracking/{index.js, store.js, i18n/en.js, i18n/bg.js, index.test.js, store.test.js}`, `frontend/src/modules/sos/{index.js, store.js, i18n/en.js, i18n/bg.js, index.test.js, store.test.js}`
- Move (`git mv`): `lib/freshness.js`, `lib/photoMarker.js`, `lib/trackerTooltip.js` and their tests to `modules/tracking/lib/`; `components/SOSBanner.vue` and its two tests to `modules/sos/components/`
- Create (re-exports, one statement each): `frontend/src/lib/freshness.js`, `lib/photoMarker.js`, `lib/trackerTooltip.js`
- Modify: `frontend/src/stores/locations.js` (becomes the facade), `frontend/src/modules/index.js` (two lines), `frontend/src/i18n/en.js`, `bg.js` (the `sos` namespace leaves)
- Modify: `frontend/src/composables/legacyLive.js` (the tracking and sos entries leave; the file is deleted when fire T510 has emptied the rest), `frontend/src/composables/useWebSocket.js` (it imports `useTrackingStore` from `../modules/tracking/index.js` for `setConnected` and no longer imports `stores/locations`; the import of the legacy list goes when that file is deleted)
- Delete: `frontend/src/components/legacyBanners.js` when it is empty (fire T505 removed the other line); then `frontend/src/components/AppLayout.vue` reads `collectBanners(MODULES)`
- Modify: the tests of section 5

**Interfaces:**
- Consumes: the live dispatch (T543), the module assembly (T403), `BANNER_PRIORITY.sos`, `lib/groups.js` at its present path.
- Produces `modules/tracking/store.js`: `useTrackingStore` (store id `tracking`) with `positions`, `trails`, `serialStatus`, `wsConnected`, `lastSyncAt`, `fromSnapshot`, `positionList`, `silentList`, `lostList`, `fetchLive()`, `fetchTrail()`, `setConnected(connected)`, `applyLocationUpdate(data)`, `applySerialStatus(data)`, `removePosition(deviceId)` (the position and the trail), `resetTrail(deviceId)`, and two things for other modules: `addUpdateHook(fn)` (`fn(data, existing) -> data` runs before the merge, in registration order) and `patchPosition(deviceId, fields)`. The snapshot key `bwm.positions.snapshot`, the 30 minute trail and every freshness rule are unchanged. `modules/tracking/index.js` exports the manifest (default) and `useTrackingStore`.
- Produces `modules/sos/store.js`: `useSosStore` (store id `sos`) with `sosAlerts`, `sosNotifications`, `hasSOS`, `fetchSOS()`, `applySOSAlert(data)`, `resolveSOS(alertId, notes)` (it calls `patchPosition(deviceId, { sos_active: false })`), `dismissSOSNotification(id)`, `forgetDevice(deviceId)`. When the store is created it registers one update hook on the tracking store (imported from `../tracking/index.js`): effective SOS is the message's flag and not manually resolved; a device that clears SOS lifts the suppression; a rising edge pushes the toast with today's name rule.
- Produces the manifests: `tracking`: `liveHandlers: { location_update, serial_status }` calling the store, `live: { onTick: () => Promise.all([store.fetchLive(), store.fetchTrail()]) }`, `depends: []`. `sos`: `banners: [{ id: 'sos', priority: BANNER_PRIORITY.sos, component: SOSBanner }]`, `liveHandlers: { sos_alert }`, `live: { setup: () => { useSosStore() }, onTick: () => useSosStore().fetchSOS() }`, `depends: ['tracking']`. Both: `routes: []`, `nav: []`, `mapLayers: []`, `panels: []`, their own `i18n`.
- Produces `stores/locations.js`: `useLocationsStore` (store id `locations`) returns the same 23 names as today, each the ref or action of the owning store (`storeToRefs` for state and getters), with `removePosition(deviceId)` calling `tracking.removePosition` and `sos.forgetDevice`.

- [ ] **Step 1: Read, then write the failing tests.** Read `stores/locations.test.js`, the two `SOSBanner` tests and the three `useWebSocket` tests. Tests, each `[T544]`. `modules/tracking/store.test.js`: `an update hook can change the message before it is merged`; `patchPosition changes one field and keeps the rest`; `removePosition drops the position and its trail`. `modules/sos/store.test.js`: `a rising SOS flag raises one toast and a second frame does not`; `a resolved alert clears the marker flag and the next asserting frame does not relight it`; `a device that clears SOS can raise a new alert later`; `the sos hook is registered before the first live message` (run the collected `setup` hooks of the real module list on a fresh Pinia, then dispatch a `location_update` with `sos_active: true` through `dispatchLive`: one toast). `modules/sos/index.test.js`: `SOS is a manifest banner at priority 10 and comes before the fire alarm` (`collectBanners(MODULES).map(b => b.id)` starts with `sos`; `contributionProblems(MODULES)` is `[]`); `sos depends on tracking and imports it only through its index`. `modules/tracking/index.test.js`: `the two manifests are valid and in the module list`; `the facade and the two stores share state` (a value assigned through `useLocationsStore().sosAlerts` is read from `useSosStore().sosAlerts`, and a position written through the tracking store is in the facade's `positionList`); `the old library paths are the moved libraries`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/modules/tracking src/modules/sos`. Expected: FAIL (`Failed to resolve import "./store.js"`).
- [ ] **Step 3: Split** the store, write the facade, move the libraries, the banner and the texts, write the manifests and the list lines, take the entries out of the legacy lists, apply the test edits of section 5.
- [ ] **Step 4: Run** `stores/locations.test.js` unedited first: it is the proof of the facade. If a case fails because a ref of another store is not writable through the facade, stop and report (section 4). Then: `cd bee-with-me\frontend; npm test; npm run build`. Expected: PASS and a clean build; `no text key was lost` and `module lib is pure` pass; the entry chunk size before and after is in the PR body (the two stores and the SOS banner enter it; no `ol`).
- [ ] **Step 5: Commit** `refactor(tracking): T544 positions and SOS get their own stores, libraries and live handlers`.

dod:
- `cd bee-with-me\frontend; npm test`
- `cd bee-with-me\frontend; npm run build`

### Task 545: the SOS toast is a panel of the sos module

**risk:** normal
**owner:** frontend-designer
**Files:**
- Move (`git mv`): `frontend/src/components/SOSToast.vue` to `frontend/src/modules/sos/components/SOSToast.vue`
- Modify: `frontend/src/modules/sos/index.js` (`panels`), `frontend/src/views/MapView.vue` (template line 2, script line 332)
- Create: `frontend/src/modules/sos/components/SOSToast.test.js`

**Interfaces:**
- Consumes: the `map-root` host of fire T504 (it sits where `<SOSToast />` is today); `useSosStore` (T544).
- Produces: `panels: [{ id: 'sos-toast', host: 'map-root', order: 10, component: SOSToast, retryKey: () => useSosStore().sosNotifications.length }]` (`retryKey` of fire T504: a toast that failed to render once is tried again with the next notification, so one render error cannot hide every later SOS toast; the banner is independent of it); `SOSToast.vue` declares the `context` prop (so it does not fall through to the root element as an attribute) and reads the sos store; `MapView.vue` has no SOS import.

- [ ] **Step 1: Read, then write the failing tests.** Read the seven `MapView*.test.js` files for a stub or a query of `SOSToast`. Tests in `SOSToast.test.js`, each `[T545]`: `shows the newest notification with its name and removes it after 10 s`; `the root element carries no context attribute`; `after a render error the next notification is shown again` (mounted through `PanelHost` with the real panel item; the component throws once, then a second notification is pushed: the toast is in the DOM); and in `modules/sos/index.test.js`: `the toast is a map-root panel and MapView does not import it`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/modules/sos`. Expected: FAIL (`Failed to resolve import "./SOSToast.vue"`).
- [ ] **Step 3: Move** the component and wire the panel.
- [ ] **Step 4: Run.** Run: `cd bee-with-me\frontend; npm test -- src/modules src/views src/platform src/architecture.test.js; npm run build`. Expected: PASS and a clean build.
- [ ] **Step 5: Commit** `refactor(sos): T545 the SOS toast is a panel of the sos module`.

dod:
- `cd bee-with-me\frontend; npm test -- src/modules src/views src/platform src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`

### Task 546: the frontend handles a thin `location_update` and a thin `sos_alert`

**risk:** normal
**owner:** implementer
**Files:**
- Modify: `frontend/src/modules/tracking/store.js`, `frontend/src/modules/sos/store.js`
- Create: `frontend/src/modules/tracking/store.thin.test.js`, `frontend/src/modules/sos/store.thin.test.js`

**Interfaces:**
- Consumes: T544.
- Produces in the tracking store: `applyLocationUpdate(data)` merges as today; afterwards, when the store held no row for `data.device_id` or the row's `user_id` differs from `data.user_id`, it calls `requestRoster()`. `requestRoster()` runs `fetchLive()` single-flight: one request at a time, and at most one more after it when a request came in meanwhile; a failure is swallowed (the resync tick repeats it). The toast name is taken from the merged row. `fetchLive()` no longer lets an old answer wipe a newer live message: it notes the time when the request starts, the store notes per device when a live message was last applied, and when the answer arrives a device whose live message is newer than the request start keeps its row (the answer's fields for that device are merged under it, so the name still arrives); every other device is replaced or dropped exactly as today. This is a deliberate fix of a race that exists today on the 45 second tick and that the refetch per new device would make frequent; it is named in the PR body.
- Produces in the sos store: `applySOSAlert(data)` shows the alert at once, filling a missing `full_name`, `rank`, `device_name` and `dev_sn` from the tracking position of that device, then calls `fetchSOS()` single-flight; a failed fetch never removes or blanks an alert that is shown.
- Both keep working with today's full messages: a field that is present wins.

- [ ] **Step 1: Write the failing tests**, each `[T546]`, with `src/api` mocked. `tracking/store.thin.test.js`: `a thin update keeps the name, the photo and the teams of a known device` (the row came from `fetchLive`; the message has only the 15 keys of section 1.4); `an unknown device triggers one refetch for a burst of frames` (three thin messages for one new device before the first request resolves: `getLivePositions` was called twice at most, and the row has its name after the request resolves); `a changed user_id triggers a refetch`; `a failed refetch leaves the marker and does not throw`; `a full message still works and asks for nothing`; `an answer that started before a new device's first frame does not remove that device` (start `fetchLive`, apply a thin update for device B, resolve the request with a list without B: B is still in `positions`; a device absent from the answer with no newer live message is dropped as today); `the kept row takes the name from the answer when the answer has the device`; `the SOS toast of a thin update uses the name of the row`. `sos/store.thin.test.js`: `a thin sos alert is shown at once and survives a failed refetch` (the alert has its `id`, the name from the position, and stays when `getOpenSOS` rejects); `the refetch completes the alert without losing its id`; `two alerts in a burst cause one refetch at a time`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/modules/tracking/store.thin.test.js src/modules/sos/store.thin.test.js`. Expected: FAIL (`getLivePositions` is not called for an unknown device).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** Run: `cd bee-with-me\frontend; npm test; npm run build`. Expected: PASS and a clean build.
- [ ] **Step 5: Commit** `feat(tracking): T546 the map joins names from the live read model when a message carries none`.

dod:
- `cd bee-with-me\frontend; npm test`
- `cd bee-with-me\frontend; npm run build`

### Task 547: the backend sends the thin payload

**risk:** security
**owner:** implementer
**Files:**
- Modify: `backend/modules/tracking/domain/payload.py`, `backend/modules/tracking/api.py`, `infrastructure/repository.py`
- Modify: `backend/modules/sos/api.py`, `infrastructure/repository.py`
- Modify: `backend/routers/test.py` (the call of the payload builder), `backend/hardware_reader/reader.py` (the arguments of the same call in `_handle_bee` and the deleted `groups_of` call; T542 is merged first, so the reader already builds its payload through the two APIs; no decode or ACK line, the hardware note of T542 is repeated in this PR body)
- Modify: the tests of section 5
- Create: `backend/tests/modules/tracking/test_thin_payload.py`

**Interfaces:**
- Consumes: T541 and T542 (merged); T546 merged and deployed to bee-dev (checked by the maintainer, a checkbox in the PR body); the device maker's answer to section 6, item 3.
- Produces: `location_update_payload` loses the parameters `roster` and `groups` and returns the 15 keys of section 1.4. `tracking.api.person_of` is replaced by `async is_person_active(conn, user_id) -> bool | None` (`SELECT is_active FROM users WHERE id = $1`; `None` when the device has no person); `groups_of` and the teams read are deleted. `sos.api.raise_sos` sends the 5 keys of section 1.4 and no longer reads `users` (the simulated path sends no `sos_alert`). The inactive-person rule is unchanged: stored, not broadcast (reader), 400 (simulate).
- Produces a constant both tests and code use: `tracking.api.PERSONAL_KEYS = frozenset({'full_name', 'rank', 'photo_url', 'phone', 'groups'})`.

- [ ] **Step 1: Read, then write the failing tests.** Read `tools/smoke.py` (`s_websocket`) and say in the PR body what step e asserts about the message. Tests in `test_thin_payload.py`, tagged `T547`: `test_location_update_has_exactly_the_thin_keys` (the 15 names); `test_sos_alert_has_exactly_the_thin_keys` (the 5 names, and `id` is a string); `test_no_live_message_of_tracking_or_sos_carries_a_personal_key` (two paths: `POST /api/test/simulate` with the mocked connection, and `reader._handle_bee` with the fakes of `gateway_fakes.py` for a fix and for a rising SOS: every `pg_notify` payload on `location_update` and `sos_alert` has no key of `PERSONAL_KEYS`; the `sos_alert` case exists on the reader path only); `test_the_reader_path_sends_exactly_the_thin_keys` (the 15 and the 5 names from `_handle_bee`); `test_an_inactive_person_is_still_not_broadcast`; `test_the_teams_and_name_reads_are_gone` (no executed statement contains `FROM user_groups` or selects `full_name`); `test_rest_still_returns_the_names` (`GET /api/locations/live` and `/sos` rows keep `full_name`).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\tracking\test_thin_payload.py -q`. Expected: FAIL (the payload still has `full_name`).
- [ ] **Step 3: Implement**; apply the test edits of section 5.
- [ ] **Step 4: Run** the DoD list and the smoke (`python tools/smoke.py`: step e PASS). Expected: PASS.
- [ ] **Step 5: Commit** `feat(tracking): T547 location_update and sos_alert carry ids and position data only`. PR body: the two payloads before and after, the 45 second note of section 1.4, R-22 (reached on the real gateway path because T542 is in), the hardware note of T542, the answer of the device maker.

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_api_simulate.py backend\tests\test_simulation.py backend\tests\test_b72.py backend\tests\test_ws_forward.py backend\tests\test_parser.py -q`

### Task 548: the tracker panel becomes a panel of the tracking module (explicit, optional)

**risk:** normal
**owner:** frontend-designer
**Files:**
- Create: `frontend/src/modules/tracking/ui.js`, `modules/tracking/components/TrackerPanel.vue`, `modules/tracking/components/TrackerPanel.test.js`
- Modify: `frontend/src/modules/tracking/index.js` (`panels`, the named export `useTrackerUi`), `frontend/src/platform/manifest.js` and `platform/map-shell/contributions.js` (optional `actions`), `frontend/src/modules/fire/index.js` (one action)
- Modify: `frontend/src/views/MapView.vue` (template lines 162 to 274; script: `viewMode`, `rankFilter`, `nowTick`, `tickTimer`, `rankFiltered`, `displayList`, `groupsWithLeaders`, `selectedDeviceId`, `selectDevice`, `reportFromRow`, `onMarkerClick`, `setViewMode`, `focusDevice`, `formatTime`, `batClass`)

**What moves and why it is planned apart.** The decision of wave 1 keeps the tracker features in the map view; modular-monolith.md section 7 gives the side panel to `tracking`. The panel is not only markup: `displayList` (the rank filter and the people or teams view) is also the list the map draws, and a row of the panel carries fire's "Report fire at this position" button. Moving it therefore needs shared state and one more contribution point. **Difference:** none intended on screen. **Risk:** the list that feeds the markers (BP-01) changes owner; a mistake shows as a marker that is filtered out while its row is visible, or the reverse.

**Interfaces:**
- Consumes: the `map` host and the map context (fire T504), `useFireUi` (fire T507, T508), `useTrackingStore`.
- Produces `ui.js`: a Pinia store `useTrackerUi` with `viewMode`, `rankFilter`, `selectedDeviceId`, `displayList` and `groupsWithLeaders` (today's computations, reading the tracking store and a `groupsMap` set by the view), `select(deviceId)`.
- Produces the contribution `actions` (optional manifest field): `{ id, target, order, labelKey, testId?, isAvailable?: (subject) => boolean, onSelect: (subject) => void }`; `collectActions(modules, target, legacy = [])` sorted by `order`, then `id`. Fire contributes `{ id: 'fire-report-at-position', target: 'tracker-row', order: 10, labelKey: <the key of today's button>, testId: 'report-fire-row', onSelect: (pos) => <today's reportFromRow with its 24 h rule> }`.
- Produces `TrackerPanel.vue` (prop `context`): the mode toggle and the `aside.tracker-panel` with their markup, classes and test ids; the 10 s `tickTimer` for the age labels, started on mount and cleared on unmount; the row actions from `collectActions(MODULES, 'tracker-row')`. `MapView.vue` passes `useTrackerUi().displayList` to `useMap` where it passed its own `displayList`, and its `onTrackerClick` callback calls `useTrackerUi().select`.

- [ ] **Step 1: Read, then write the failing tests.** Read the seven `MapView*.test.js` files for every query on `.tracker-row`, `.tracker-panel`, `[data-testid="report-fire-row"]`, the rank filter and the mode toggle, and keep each. Tests in `TrackerPanel.test.js`, each `[T548]`: `rows come out by urgency and show name, MGRS, age and battery`; `the rank filter narrows the rows and the list the map gets`; `the teams view shows one leader row per team`; `the age label of a row changes class when its position goes stale, without a new message` (fake timers, 10 s tick); `a selected row offers the row actions of the modules`; `unmount clears the tick timer`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/modules/tracking/components`. Expected: FAIL (`Failed to resolve import "./TrackerPanel.vue"`).
- [ ] **Step 3: Move** the blocks and the state; the CSS rules move with their elements.
- [ ] **Step 4: Run** the seven unedited `MapView` test files and the rest. Run: `cd bee-with-me\frontend; npm test; npm run build`. Expected: PASS and a clean build. A `MapView` test that would need an edit stops the task.
- [ ] **Step 5: Commit** `refactor(tracking): T548 the tracker panel is a panel of the tracking module`.

dod:
- `cd bee-with-me\frontend; npm test`
- `cd bee-with-me\frontend; npm run build`

### Task 549: tracker, trail and checkpoint layers become the tracking map entry (explicit, optional)

**risk:** normal
**owner:** frontend-designer
**Files:**
- Create: `frontend/src/modules/tracking/map/layers.js`, `modules/tracking/map/index.js`, `modules/tracking/map/trackerLayers.test.js`
- Modify: `frontend/src/modules/tracking/index.js` (`mapLayers`), `frontend/src/modules/mapEntries.js`
- Modify: `frontend/src/composables/useMap.js` (lines 149 to 243, 259 to 300, 383, 399 to 402, 502 to 640, the tooltip handler, 753 to 788, 867 to 870), `frontend/src/views/MapView.vue` (one note for a failed install), `frontend/src/i18n/en.js`, `bg.js` (one key)

**What moves and why it is planned apart.** This is the move the wave 1 decision postponed ("tracker, repeater, weather and basemap layers stay in the facade"). It is the last piece of `tracking` on the map and the largest single cut of `useMap.js` (about 350 lines). **Difference:** the three layers are created by `shell.install` instead of the facade; `staleTimer` starts in `shell.onMounted` and is cleared by the entry's `dispose`; a failed install no longer takes the whole map down, so it has to be made visible (below). **Risk:** BP-01 directly: a marker that is not drawn, or not restyled when it goes stale, is a person the operator cannot see. The repeater layer, the measure layer, the graticule, the basemaps and the weather layer stay in the facade.

**Interfaces:**
- Consumes: `shell.install`, `shell.onMounted`, `shell.onClick`, `shell.onPointerMove` and the `ctx` of T422 (shape unchanged); `Z.trail`, `Z.checkpoints`, `Z.trackers`; the libraries of `modules/tracking/lib/`.
- Produces `map/layers.js`: `TRACKING_MAP_LAYERS = [{ id: 'tracking-trail', zIndex: Z.trail }, { id: 'tracking-checkpoints', zIndex: Z.checkpoints }, { id: 'tracking-trackers', zIndex: Z.trackers }]`. `map/index.js`: default export `{ name: 'tracking', layers: {...}, setup: setupTrackingMap }`; `setupTrackingMap(shell, ctx)` returns `{ api: { setPositions(list), setTrails(trailMap), setGroups(groupsMap), setShowPhotos(on), setTrailVisible(on), setCheckpointNumbers(on), refreshMarkers(list), trackerHit(pixel) }, dispose }`. It owns the marker, photo, trail and checkpoint styles, the tooltip overlay and its `always` pointer handler, the tracker click handler (`order` 10, today's rule: it runs only when a fire click callback is registered and reports `null` to it first), the photo-loaded restyle and the 60 s `staleTimer`.
- Produces in `useMap.js`: the facade keeps its eight parameters and 22 returned names; its watchers on `positionList`, `trails` and `showPhotos` call the entry's api; `ctx.trackerHit` reads the entry's `trackerHit` at call time; `makeMarkerStyle` and `makePhotoMarkerStyle` stay exported from `useMap.js` as re-exports of the entry (two tests import them there). When the tracking install failed, `refreshMarkers` returns `false`.
- Produces in `MapView.vue`: when `refreshMarkers` returns `false` a note with `role="alert"` and the new text `map.trackerLayerFailed` (EN "The tracker layer could not be loaded. Reload the page.", BG "Слоят с тракерите не се зареди. Презаредете страницата.") is shown in the place of the stale-feed banner (BP-03). This is the one new text of the plan.

- [ ] **Step 1: Read, then write the failing tests.** Read the eight `useMap.*.test.js` files; they call the real composable and are the net (`b50`, `b54`, `b56`, `photo`, `hqFallback`, `interaction`, `fire`, `zones`). Tests in `trackerLayers.test.js`, each `[T549]`, with a shell as in T422: `the three layers are registered with z-index 5, 6 and 10`; `positions set before mount are drawn after mount`; `a position that goes stale is restyled by the 60 s timer without a new message` (fake timers); `dispose stops the timer and removes the tooltip overlay`; `a tracker under the pointer shows the tooltip in every mode`; `a failed install makes refreshMarkers return false` (the entry's `setup` replaced by one that throws).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/modules/tracking/map`. Expected: FAIL (`Failed to resolve import "./index.js"`).
- [ ] **Step 3: Move** the code in this order, running `src/composables` after each: styles; sources, layers and upserts; tooltip and click handlers; the timer and the watchers; the failure note.
- [ ] **Step 4: Run** the eight unedited `useMap` test files, the seven `MapView` test files and the rest. Run: `cd bee-with-me\frontend; npm test; npm run build`. Expected: PASS and a clean build; the entry chunk has not grown by OpenLayers.
- [ ] **Step 5: Commit** `refactor(tracking): T549 tracker, trail and checkpoint layers are the tracking module's map entry`.

dod:
- `cd bee-with-me\frontend; npm test`
- `cd bee-with-me\frontend; npm run build`
