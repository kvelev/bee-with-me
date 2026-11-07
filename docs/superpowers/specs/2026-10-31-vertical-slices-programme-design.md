# Vertical slices programme: design

**Date:** 2026-10-31
**Status:** Approved by the maintainer on 2026-10-31 (sections 6 and 9 record the answers); the owner's questions are in section 9
**Builds on:** [ADR 17](../../../Architecture/decisions/0017-vertical-slice-modules.md) (Accepted),
[ADR 18](../../../Architecture/decisions/0018-transactional-outbox.md) (Proposed),
[ADR 19](../../../Architecture/decisions/0019-architecture-tests.md) (Proposed),
[modular-monolith.md](../../../Architecture/application/modular-monolith.md) (target structure, migration
steps 0 to 5), field-exercise-findings.md (not in this repository)
(order of work: vertical slices first)

This document describes the whole programme, not one feature: how the code base gets from today's layered layout to
modules as vertical slices, what has to be true before the first file moves, and how the parallel change from
offline-first to online-first is carried along. The target structure itself is **not** redefined here; it is the
modular-monolith document. This document adds what that document leaves open and what the code base looks like on
2026-10-31.

---

## 1. Intent and why

Several people and agents now work on the code at the same time, and every one of them ends up in `MapView.vue`,
`useMap.js`, `main.py` or the two i18n files. Modules write into each other's tables. Each planned capability
(generic field signal FX-04, wind, APRS, Meshtastic, AI situation report) would add to the same files. The owner
decided on 2026-10-21 that the vertical-slice restructuring comes before any of them.

At the same time the owner has decided that the system moves from offline-first to **online-first** (Starlink is
standard in the field, and a hosted environment exists). The parts of the code that this touches first, the live
channel `/ws`, the photo files under `/uploads`, CORS and transport security, are exactly the parts that the
restructuring moves into `platform/live` and `identity`. Doing the two separately would mean touching the same
files twice.

Success looks like: an agent assigned to one module changes only that module's folders and its tests; a new module
is a new folder plus one line in a list; the live channel is authenticated and encrypted; the whole thing happened
without a single behaviour change the field operator can notice, proven by tests that existed before the move.

## 2. Goals, non-goals, anti-goals

**Goals**

1. The code base matches modular-monolith.md sections 3 to 8 at the end, with an empty architecture-test allowlist.
2. Every step ships as one pull request to the owner's `develop` branch that is green in CI and reviewed by the
   breaker and, where security paths change, the security reviewer.
3. A regression safety net exists **before** the first move and stays green through every step.
4. The live channel carries no personal data beyond IDs by the end of step 4 (thin payload, R-22). Authentication
   and TLS of the live channel are **not** part of this programme (maintainer decision, 2026-10-31): they wait for a discussion
   with the person who builds the devices. The research report stays as the input to that discussion.
5. The architecture documents are updated as decisions are taken: ADR 18 and 19 move to Accepted when their step
   is merged; the online-first ADR is proposed by the architecture owner when the owner and the device maker have
   talked, not by this programme.

**Non-goals**

- Changing what the system does for the operator. No new capability ships inside this programme; FX-04 is the first
  module built *on* the result, not part of it.
- Splitting into several processes or adding a cache or message broker service (ADR 6 stays).
- Re-deciding the module catalogue of modular-monolith.md section 4. Additions found in the code are recorded
  (section 6 below), not debated.
- Packaging or installer work (ADR 14 and ADR 20 are the owner's track).

**Anti-goals** (the programme has failed even if the tests are green)

- A frame from a device is lost or acknowledged before it is stored at any point of step 3 (BP-01, R-06).
- An alarm (SOS or fire) arrives later, or not at all, because a dispatcher or queue sits on its path (BP-02).
- A deletion of personal data stops half-way without anyone seeing it (DP-03, BP-03).
- The field laptop can no longer start without internet after the online-first changes (the start itself stays
  offline-capable; only optional sources need the network).
- Work on `main` or `develop` directly, or a force-push to either.

## 3. Constraints

| Constraint | Source |
|------------|--------|
| Branch from `upstream/develop`; pull requests go to `develop`; `main` receives only releases. Nothing is pushed to either directly. | owner's `CONTRIBUTING.md`, maintainer decision 2026-10-31 |
| CI runs on every PR: pytest with `--require-db` against PostGIS, PowerShell script tests on Windows, vitest, build, npm audit. A red CI blocks the merge. | `.github/workflows/ci.yml` |
| Schema changes are new numbered files in `backend/db/migrations/`, additive, reviewed by the migration reviewer; `0006` and `0007` already exist on `develop`. | ADR 10, ADR 20 |
| Step 3 (gateway, tracking, sos) changes the hardware path and must be validated on the real gateway before merge. The agent never runs anything against a field machine. | ADR 17, CLAUDE.md |
| Front-end files (`.vue`, `.css`, components, views) are changed only by the `frontend-designer` agent. | CLAUDE.md hooks |
| Architecture documents are owned by the architecture owner; implementation sessions propose text, they do not rewrite principles. | maintainer decision |
| Owner-written files (`README.md`, `CHANGELOG.md`, `todo.md`, `docs/PROTOCOL.md`, `docker-compose.yaml`) are touched only after asking. | `.claude/protected-paths.txt` |
| Every test carries a tag: pytest `@pytest.mark.Trait("Task", "T<n>")`, vitest `[T<n>]`; bugs `B<n>`. | CLAUDE.md |
| Test runs are slow (12 min backend locally). Tasks that touch 3 to 5 files do not run the suites individually; batches do. | maintainer decision |
| Dependencies are added with a version. The architecture-test tools are not installed yet on either side. | CLAUDE.md, checked 2026-10-30 |

## 4. State of the code on 2026-10-31

- `upstream/main` is what has passed a field test. `upstream/develop` is 16 commits ahead (ADR 20 separate update
  script, migrations 0006 and 0007, `reader.py` matches `device_type`, dependency bumps). `upstream/main` has 13
  commits that `develop` does not (B62 to B67, field-exercise findings). The owner reconciles those; this programme
  starts from `develop` as it is.
- ADR 18 on `develop` has an accidental text corruption ("GWIS must not run twice", "## DecisionGWIS").
- Backend: 841 tests pass locally, 180 skip without PostgreSQL (73 are `db`-marked and run in CI). Frontend: 362
  tests pass. Coverage is uneven: `fire`, `settings`, auth, simulation, weather, the frame parser and the
  migration runner are well covered; `teams` has no API test, `tracking` only `/live`, `sos` none, `devices` only the
  permanent delete (develop adds `test_api_devices.py`), `people` delete cascade and Excel import none, export CSV and
  GeoJSON none, `reader.py` handlers and `hid_reader.py` none. Frontend: `UsersView`, `GroupsView`, `DevicesView`,
  `ExportView`, `LoginView`, `FieldReportForm`, `SuppressionZoneForm` have no tests.
- Cross-module writes today: `routers/users.py` into `location_events` and `sos_alerts`; `routers/devices.py` into
  `sos_alerts`, `location_events`, `repeater_events`, `fire_alerts`; `routers/users.py`, `devices.py`, `settings.py`
  call `fire.repository` and `fire.service` directly **in the same transaction** as their own write (deactivating a
  person or device, or clearing HQ, resolves the open fire alerts by that admin); `main.py` writes `users` (default
  admin) and `location_events` (retention) and wires the fire poller to settings; `reader.py` joins `users`,
  `user_groups`, `groups` to build the live payload; `simulation.py` seeds `users`, `devices`, `groups`, `user_groups`
  and writes `location_events` and `sos_alerts`.
- Hardware path today: `hid_reader.py` marks a frame as seen **before** `_handle_bee` stores it, the handlers run
  statement by statement (no single transaction), and an unknown-device frame is still acknowledged (R-06, ES-23).
- External contracts that name files: `uvicorn backend.main:app` (start scripts, Dockerfile), `python -m
  backend.db.migrate status|up` (start, update and script tests), `backend/version.py` with a literal `APP_VERSION`
  line parsed by `sed` in `ci.yml` and `release.yml`. All test runners (CI, the owner's pre-commit hook, the tooling's
  stop checks, the `test-author` write scope) are pinned to `backend/tests/`.
- The owner's hosted **develop environment** is rebuilt and deployed on every merge to `develop`
  (`deploy-develop.yml`, `deploy/k8s`): backend behind an ingress with `--proxy-headers`, no gateway,
  `ENABLE_TEST_ENDPOINTS=true` as the only data source. No client there is on loopback.

## 5. The programme in four phases

### Phase 0: sync and housekeeping (one pull request, no code change)

1. Fork side: create `develop` from `upstream/develop`, push to `origin`. All programme branches are
   `feature/vs-<step>-<module>` off `develop`.
2. Commit the ADR 17 status change (Proposed → Accepted, already made locally by the maintainer). Fix the ADR 18 text
   corruption. Both are text-only architecture changes; the architecture owner is told.
3. Bring the tooling's `CLAUDE.md` up to date: CI exists; PRs target `develop`; the base for all work is `develop`.
4. B66 and B67 (map recovery, IPv4 loopback) are field-tested fixes that `develop` does not have. They are listed
   for the owner as cherry-pick candidates; this programme does not merge them itself.

### Phase 1: regression safety net (two or three pull requests, tests only)

Characterisation tests written against the code **as it is on `develop`**, through the same seams the existing tests
use (FastAPI test client with the mocked connection; `db`-marked tests for SQL that matters; vitest with mounted
components). They pin behaviour, not structure, so that they survive the move unchanged apart from import paths.

| Target module | Tests to add (behaviour pinned) |
|---------------|--------------------------------|
| `teams` | list with and without members, create, update, deactivate, delete, add and remove member, leader flag; role checks |
| `tracking` | `/trail` bounded by `assigned_at` and `minutes`; `/history` filters and limits; `/live` freshness horizon and inactive-user filter (`db`) |
| `sos` | `/sos` list; resolve once, resolve twice is a no-op; role checks |
| `devices` | create with per-type serial (0006), assign and reassign, deactivate, reactivate, permanent delete cascade order and the alarm lock (`db`), repeater site location (0007) |
| `people` | delete nulls `location_events.user_id`, `sos_alerts.user_id` and `resolved_by` (`db`); deactivate resolves rescuer alerts; Excel import happy path and a malformed sheet; photo upload |
| `gateway` | `_handle_bee`: unknown device, no-fix frame anchoring, SOS edge trigger, payload content and `pg_notify` channel; `_handle_repeater`; `hid_reader` frame reassembly and ACK order (mocked HID) |
| `reporting` | CSV and GeoJSON content and filters; role check |
| `identity` | default admin creation and `INITIAL_ADMIN_PASSWORD` (exists in `test_simulation.py`, moved here) |
| `platform/live` | `/ws` endpoint accepts, forwards, drops a dead client; listener reconnect (exists partly in `test_ws_forward.py`) |
| frontend | `UsersView`, `GroupsView`, `DevicesView`, `ExportView`, `LoginView`: render, list, main action, error state; `SOSBanner` resolve; `useWebSocket` dispatch table (every message type reaches its store) |

Rules for these tests:

- They stay under `backend/tests/` for the whole programme, in `backend/tests/modules/<module>/` (CI, the owner's
  pre-commit hook and the tooling scopes are all pinned to that path and the workflow file is owner-protected). Frontend
  tests stay next to their component; the `*.test.js` glob follows them when the module moves.
- They pin **outcomes**, not transaction boundaries or statement order: "after deactivating the person, the alert is
  resolved and `resolved_by` is the admin", not "both statements ran in one transaction". Step 4 may make that
  reaction asynchronous (section 9, question 3) without rewriting the test beyond "run the dispatcher once".
- Where today's behaviour contradicts a principle (the hardware path, section 4), the test asserts the **intended**
  behaviour and is marked expected-to-fail with the step that fixes it, so the suite is green and the debt is visible.
  The `test-author` rule applies: no asserting current behaviour just because the code does it.

Tags: `T1xx` for phase 1. Done when the suites are green locally (without DB) and in CI (with DB), and every row above
has at least one test.

### Phase 2: the migration, steps 0 to 5 of modular-monolith.md section 9

One pull request per step (step 5 may be split per module). Each PR: moves the module, removes its allowlist lines,
keeps old import paths as thin re-exports until step 5, updates the module's own `en.js` and `bg.js`, passes breaker
and security review where relevant, and **passes the smoke gate before it is merged** (maintainer decision, 2026-10-31): a merge into
`develop` builds the images and deploys them to the testers' environment (bee-dev.butters.monster), so the app must
start and work end to end before the merge, not after. CI today never builds or starts the images on a pull request
(`deploy-develop.yml` builds them only after the push to `develop`), so a broken Dockerfile or start-up is found by the
testers. The smoke set and how it runs are defined in the step-0 plan. Additions to the written steps, found in the code:

- **Step 0** also decides and pins the architecture-test tool (section 7 below), adds `backend/tests/architecture/`
  and `src/architecture.test.js` with the allowlist of today's violations, and introduces the manifest contract. The
  `database.py`, `json_columns.py`, `config.py`, `auth.py` (token functions only) and `ws.py` move to the shared
  kernel package **`backend/core/`** (not `platform/`: that name shadows Python's standard `platform` module whenever
  `backend/` itself is on `sys.path`; maintainer decision 2026-10-31; modular-monolith.md 3.1 is corrected, the frontend keeps
  `src/platform/`). **Three files do not move and are not re-exports:** `backend/main.py` (uvicorn target),
  `backend/db/migrate.py` (`python -m backend.db.migrate` in start, update and script tests) and `backend/version.py`
  (parsed by CI and the release workflow). modular-monolith.md section 3.1 lists `migrate.py` and `version.py` under
  `platform/`; that line is corrected, the kernel imports them. `main.py` keeps `_warn_insecure_defaults` and the
  lifespan skeleton; everything else it does today is claimed by a module in later steps. `platform/live` is a
  move of today's `ws.py`: no authentication hook, no origin check, no behaviour change (section 5, phase 3).
- **Step 1** (`settings`) also removes the `settings_router.after_change` hook from `main.py`: `settings` publishes
  `SettingsChanged` on its own; until the outbox exists (step 4) it calls `fire.api.request_evaluation` directly and
  the allowlist carries that line.
- **Step 2** (`fire` + map-shell) is the first frontend module; the `frontend-designer` owns the map-shell extraction
  and the fire layers, banner, popup and context-menu contributions. `FieldReportForm` moves with `fire` (FX-04 later
  moves it out).
- **Step 3** (`tracking`, `sos`, `gateway`) carries the thin payload. Thin applies here to `location_update` and `sos_alert`; `fire_alert*` payloads keep `full_name` and `rank` until
  step 4 (the owner put them there on purpose: the operator needs them in the banner) and go thin when the
  `people_changed` / `devices_changed` messages exist. `simulation` is touched here too, because it writes
  `location_events` and `sos_alerts` today; it must call `gateway` (or `tracking.api` and `sos.api`) instead.
  This step also **fixes the hardware path** (maintainer decision, 2026-10-31): the frame is marked seen only after it is stored, the
  position and the SOS are one transaction with the `pg_notify` inside it, and an unknown device gets no ACK (R-06,
  ES-23, modular-monolith.md 5.1). Hardware validation on the real gateway is a named step in the PR with the owner,
  who may still split the step into "move only" and "fix" when it starts.
  Frontend: `locations` store splits into `tracking` and `sos` stores; frontend `people`, `teams` and `devices` modules
  are created **in this step, ahead of their backends** (they only need the REST endpoints that exist) and supply
  names, teams and photos to the map; `SOSBanner` and `SOSToast` move to `sos`.
- **Step 4** (`devices`, `teams`, `people` + outbox) needs migrations `0008` (outbox, inbox, dead_letter) and `0009`
  (soft-delete marker on `users`), both through the migration reviewer; the `PersonDeleted` flow replaces the direct
  SQL in `routers/users.py` and `routers/devices.py`. The synchronous "deactivate resolves fire alerts" reactions
  become events (`PersonDeactivated`, `DeviceDeactivated`, `HQCleared`, payload: IDs and the acting admin's ID) that
  `fire` subscribes to (maintainer decision, 2026-10-31); they are added to modular-monolith.md section 5.4. **Every event carries a
  correlation ID** (maintainer decision, 2026-10-31): the publishing request's ID (a request-ID middleware in `core/`, taken from an
  incoming `X-Request-ID` header or generated), stored on the `outbox`, `inbox` and `dead_letter` rows, written in
  every log line of the publisher, the dispatcher and each handler, and returned in the response header, so one
  admin action can be traced from the HTTP call through every reaction. Background publishers (poller, retention)
  generate their own per-tick correlation ID. `simulation` seeds people, devices and teams through their `api.py` (graph edges
  `simulation → people, devices, teams` are added to section 4.2; until this step the seed is allowlisted). The
  default-admin creation moves to `identity`, which calls `people.api`. `fire_alert*` payloads go thin here.
- **Step 5 and the offline map selection** (added 2026-11-07, PR #53 of the device maker): `develop` now has
  `frontend/src/views/SelectOfflineMap.vue`, the `offline-map-changed` window event in `MapView.vue` and a separate
  Node service `tile-server/` (`server.js`, README). They belong to the `maps` module: the view and the basemap
  switch move with the map-shell/`maps` contributions (the window event becomes a map-shell contribution, not a
  global event), and `tile-server/` stays outside `backend/` but is named in the `maps` manifest as its external
  collaborator. No ADR describes it yet; ADR 21 or a `maps` note must say whether it replaces the tileserver-gl
  container and how it fits the offline-first to online-first move.
- **Step 5** also creates a backend `weather` module (`routers/weather.py` exists with 10 tests; the catalogue lists
  weather as frontend-only) and places `maps` (tiles), `reporting`, `simulation`, `identity`. The re-exports go, the
  allowlist is empty, ADR 18 and ADR 19 become Accepted.

### Phase 3: online-first track (research done; implementation deferred)

1. **Research** is done: [2026-10-31-ws-security-online-first.md](../../research/2026-10-31-ws-security-online-first.md)
   compares five ways to authenticate `/ws` with the JWT we have (recommends the first message after connect carrying
   the token, re-sent after each refresh, plus an `Origin` check), five transport options without a CA certificate
   (field laptop: `localhost` needs none, otherwise a private CA such as Caddy `tls internal`; hosted: cert-manager
   with a bought domain; Let's Encrypt is impossible behind Starlink CGNAT), explains why a client id and secret adds
   nothing in a browser SPA, and lists nine risks in today's code.
2. **No security implementation in this programme** (maintainer decision, 2026-10-31). The design of the live channel has to be
   agreed with the device maker, who builds the devices and the gateway, first (the gateway and future device-side clients are affected by
   any authentication on the channel). `platform/live` moves as it is; `/uploads`, CORS and the login rate limit stay
   as they are; ADR 15 stays in force.
3. **What the programme still does for that future work:** the thin payload (step 3 and 4) removes phones and photo
   paths from the open channel (R-22) and is a prerequisite of any authentication design; `platform/live` is the one
   place where the hook will go later. The research report's risk table is handed to the architecture owner for the
   risk register.
4. **Candidate the owner may approve separately, outside this programme:** the bounded broadcast (a send timeout per
   client so one slow client cannot delay alarms to the others, BP-02). It is a robustness fix, not security, but it
   changes behaviour and is therefore not slipped into a move PR.

## 6. Decisions taken in this document (the maintainer's calls, to confirm)

| Topic | Call |
|-------|------|
| Base branch | `upstream/develop` as it is; B66 and B67 are the owner's cherry-pick decision |
| Order | Phase 0, then phase 1 fully, then phase 2 steps in the written order; phase 3 research starts at once, its implementation waits for its step |
| Regression test style | Characterisation tests through the existing seams, tagged `T1xx`, kept in today's `backend/tests/` and `src/**/*.test.js` locations until the module moves them |
| `weather` | A backend module in step 5 (it exists and has tests); the catalogue text is corrected |
| `simulation` | Stays a module; stops writing `location_events` and `sos_alerts` directly in step 3 |
| `main.py` leftovers | Default admin → `identity` (step 4); retention → `tracking.tasks` (step 3); fire wiring → `fire.module` (step 2) |
| Live-channel security | Out of scope (maintainer decision, 2026-10-31): researched, not implemented; waits for the device maker |
| Hardware path (step 3) | Fixed, not preserved: ACK after store, one transaction, no ACK for unknown devices; phase 1 pins it as expected-to-fail (maintainer decision, 2026-10-31) |
| Cross-module reactions | Outbox events, eventually consistent, every event with a correlation ID traced through logs and tables (maintainer decision, 2026-10-31) |
| Kernel package name | `backend/core/`; frontend `src/platform/` unchanged (maintainer decision, 2026-10-31) |
| Test location | `backend/tests/modules/<module>/` for the whole programme; frontend tests next to their component |
| Frozen files | `backend/main.py`, `backend/db/migrate.py`, `backend/version.py` stay where they are; modular-monolith.md 3.1 corrected |
| Thin payload scope | `location_update` and `sos_alert` in step 3; `fire_alert*` in step 4 |
| Frontend `people`/`teams`/`devices` | Created in step 3 ahead of their backend modules |
| Simulation seed | Allowed to call `people`, `devices`, `teams` APIs (graph edges added); allowlisted until step 4 |
| Done criterion | A PR reaches `develop` only after basic smoke tests pass on the change (bee-dev must keep working); maintainer decision, 2026-10-31 |
| Execution method | superpowers:subagent-driven-development per task, with this repo's agents (`implementer`, `test-author`, `frontend-designer`, `breaker`, `security-reviewer`, `ef-migration-reviewer`); tests batched per the test-run policy |

## 7. Left to the builder

- Architecture-test tool for the backend: `import-linter` (contracts in configuration, widely used) or
  `pytest-archon` (rules in test code). Pick one in step 0, pin it, and write the SQL-ownership scan and the manifest
  completeness check as plain pytest either way. Frontend: `dependency-cruiser` pinned, driven from a vitest test.
- Shape of the manifest (`module.py` fields, `index.js` fields) and of the allowlist file.
- Exact split of `useMap.js` into map-shell and module layers; `frontend-designer` decides within section 7 of
  modular-monolith.md.
- Outbox dispatcher details (poll interval, backoff, retention) within section 5.2 of modular-monolith.md.
- Test fixtures for the `db`-marked tests (the existing `conftest.py` pattern).

## 8. Live-channel design

Deferred. Input: the research report of phase 3. Owner: the owner together with the device maker.

## 9. Open questions for the owner (answers change what gets built)

1. ~~**Develop environment.** Is "the develop environment still works after the merge" a done criterion of every step?~~
   **Answered (maintainer decision, 2026-10-31): yes, and earlier than asked.** The change must already work *before* it reaches
   `develop`: every PR into `develop` has passed basic smoke tests first, because a merge deploys to the testers on
   bee-dev.butters.monster. See the smoke gate in section 5, phase 2.
2. **Step 3 hardware validation:** who runs it, on which gateway, and in which window? The step fixes R-06 (section 5),
   so the validation covers ACK timing, retransmission after a failed store, and unknown-device frames.
3. B66 and B67: cherry-pick to `develop` before this programme's PRs, or let them come with the next
   `main` → `develop` merge?
4. For the later live-channel discussion with the device maker (not blocking): does "the start works offline"
   survive as a principle; is a domain for Let's Encrypt acceptable or must a private CA do; is the field laptop ever
   reached from another device? The research report has the trade-offs.
6. **Tile server (2026-11-07).** What is `tile-server/` (Node, from the device maker's PR #53) in the architecture: a
   replacement for the tileserver-gl container, an addition, or a field-laptop-only tool? Is it started by
   `start.ps1|sh` on every machine, and does it run on bee-dev? It is a second runtime (Node) next to Python.
7. **Develop deploy is red (2026-11-07).** `npm audit --omit=dev --audit-level=high` fails on push to `develop`
   (`vue-i18n ^9.13.1`); fix = v11, separate PR. Until it is green bee-dev gets
   no new image, which also blocks the smoke gate (section 5, phase 2) from being meaningful.
5. FX-04 (clarified by the maintainer, 2026-10-31): the field signal becomes **generic**; the operator at the laptop says what the
   obstacle is (fallen tree, fire source, other) when it arrives, so the category is chosen on the laptop, not sent by
   the device. Still open for the owner: does a signal classified as "fire" also appear on the fire layer and count for
   the fire alarm, or does it stay only on the field-signal layer? (Not needed for this programme; needed before FX-04.)
