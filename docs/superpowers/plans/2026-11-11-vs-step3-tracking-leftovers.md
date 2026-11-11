# Vertical slices, step 3: what is left of `tracking` on the backend (retention as a module task, the simulation through the gateway) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take the daily clean-up out of `main.py` into the modules that own the data (`tracking.tasks` for old positions, `fire.tasks` for the fire data), and make the simulation feed `gateway.api` instead of writing positions and alerts through `tracking.api` and `sos.api`, so no `module_edges` row is marked `until: 3` when step 3 is recorded as complete.

**Architecture:** One small kernel helper runs a job shortly after start and then daily; each module wraps its own clean-up in it and lists it in its manifest, so `main.py` starts neither. The simulation encodes a real Cmd=30 frame and hands it to `gateway.api.store_frame`, which runs the same handler a radio frame runs, without the duplicate filter and without an ACK, and tells the caller what it did.

**Tech Stack:** Python 3.11+, FastAPI, asyncpg, pytest. No new dependency, no migration.

**Spec:** [`docs/superpowers/specs/2026-10-31-vertical-slices-programme-design.md`](../specs/2026-10-31-vertical-slices-programme-design.md) sections 5 ("Step 3": the simulation calls `gateway`), 6 ("`main.py` leftovers": retention to `tracking.tasks` in step 3; "`simulation`"); `Architecture/application/modular-monolith.md` 4.1, 4.2, 5.1; ADR 17, 19. Overview: [`2026-11-11-vs-wave3-overview.md`](2026-11-11-vs-wave3-overview.md).

**Base:** `upstream/develop` at `d174ce3`. Both tasks need T600 of the gateway plan (`regen.py --check`). T621 also needs T604 of the gateway plan and T547 of wave 2 merged.

## Global Constraints

- The decisions of the gateway plan's Global Constraints apply. Tags: `T62x`.
- **Hardware:** both tasks are **safe without hardware**. Neither edits a function pinned by T601; T621 calls the reader's handlers through `gateway.api` and edits none of them.
- Retention deletes personal data (DP-03): every clean-up keeps its own `try`/`except`, its own log lines (texts unchanged) and its own pooled connection, so one failing job never stops the next and never fails silently.
- The first pass still runs 30 seconds after start and then every 86 400 seconds (a field laptop is switched off between operations).
- `ENABLE_TEST_ENDPOINTS` rules are unchanged: the simulation routes exist only with the flag, and only an admin may call them.
- Schema: nothing. If a later decision wants a table (for example a frame log), it is a new numbered migration, additive, reviewed by `ef-migration-reviewer`, with a number after the two reserved by step 4.

## Review Focus

1. The daily clean-up stops running after the move and nobody notices for weeks: the manifests list the two tasks, and one test goes from the manifest through `start_module_tasks` and the real `run_periodic` with a fake sleep to the log line of the first pass (`test_the_manifest_task_runs_its_first_pass_after_30_seconds`, T620); `test_periodic.py` pins the 30 and 86 400 second sleeps.
2. One failing clean-up blocks the others (today each has its own `try`): a test makes the position delete raise and still sees the three fire jobs run (T620).
3. The simulated SOS goes quiet: through the real handler an alert opens on a rising edge only. A test mode that is stopped and started again without Reset would find the last stored flag already true and never raise the alarm again, so the start sends one frame without SOS for every SOS persona first (T621, `a second start without a reset raises the alarm again`).
4. A stale or lost demo tracker looks fresh: the past time must reach `received_at` (T621, `a past contact time is stored as received_at`).
5. The demo trackers vanish from bee-dev because a device row misses a column the new path reads: `seed` returns the columns `record_position` needs, and a test runs `seed` rows through it (T621).

---

## 1. Design

### 1.1 The clean-up today and after

`main._cleanup_old_locations` (started by `lifespan` as `cleanup_task`) does four things in one loop: the `DELETE` of old `location_events` (the only SQL `main.py` still holds for a module table; `allowlist.json` has it as `sql_writes`, `main.py`, `location_events`, `DELETE`), then `fire.api.anonymise_alerts`, `anonymise_hotspots` and `prune_fire_data`. Only the first is `tracking`'s; the other three are a leftover of `fire` that wave 2 left in `main.py`.

| Job | After | Log lines (unchanged) |
|-----|-------|-----------------------|
| delete old positions | `tracking.infrastructure.repository.delete_positions_older_than(conn, days) -> int` (the statement copied unchanged), run by `tracking.tasks.cleanup_positions_once()` | `Location cleanup: removed %d events older than %d days`, `Location cleanup failed: %s` |
| anonymise resolved alerts, anonymise hotspots, prune fire data | `fire.tasks.cleanup_fire_data_once()`: the three blocks moved as they are | the six fire lines of today |
| the loop | `backend/core/periodic.py`: `run_periodic(job, *, first_delay=30, period=86_400)` | `%s failed: %s` for an error that escapes a job (none does today) |

`tracking.tasks.cleanup_positions()` and `fire.tasks.cleanup_fire_data()` are the manifest tasks; each is `await periodic.run_periodic(<its _once function>)` with `periodic` looked up at call time, so a lifespan test parks both by patching `periodic.run_periodic` once. The order between the two modules is no longer fixed (two tasks instead of one loop); nothing depends on it: the position delete and the fire jobs touch different tables. Both tasks are cancelled and awaited by `stop_module_tasks` before the pool closes (today's `cleanup_task` is cancelled and not awaited).

The allowlist row of the position delete says `until: 5`, so T690 does not need T620; it is done in this wave because the spec's section 6 puts retention in step 3 (overview, M3).

### 1.2 The simulation through the gateway

| Today (`routers/test.py`, `record_position`) | After |
|-----------------------------------------------|-------|
| `simulate` reads the device by id (`id`, `user_id`); `seed` returns rows with `id`, `user_id`, `is_active` | both read `id`, `user_id`, `dev_sn`, `device_type` and `user_active` (a join on `users`; `TRUE` when the device has no person); a device that is not a `bee` is a 400 `Device is not a bee` (today a repeater's id is accepted and gets a position row) |
| `tracking_api.insert_simulated_position` with `at` as `recorded_at` and `received_at` | `frame = gateway_api.parse_frame(gateway_api.encode_bee_frame(...))`, then `outcome = await gateway_api.store_frame(conn, frame, received_at=at or now)`; the frame's `recorded_at` is the same time cut to the second (the frame carries no fraction) |
| `sos_api.open_simulated_alert` (an `INSERT ... WHERE NOT EXISTS`, no live message) | the handler's own rule: an alert on the rising edge, with the `sos_alert` message, so the banner and its sound now play for testers as for a real SOS |
| reads the person, answers 400 for an inactive one **after** the insert | answers 400 `User is inactive` from `user_active` before anything is stored |
| builds the payload from the request's `sos_active`, deletes `course_deg`, publishes | the handler publishes: `sos_active` is the effective flag (is an alert open), `course_deg` is in the message (the simulation sends `0`), `raw_flags` in the row is the real flag byte instead of `0` |
| a no-fix frame is given the last position by the caller | the frame says `V`; the handler anchors it to the last fix itself |
| returns `{'inserted': <row id>, 'lat', 'lon', 'mgrs'}` | returns `{'inserted': True, 'lat', 'lon', 'mgrs'}` (the handler returns no row id; nothing in `tools/`, `frontend/src` or `backend/` reads the field: `git grep -n "inserted" -- tools frontend/src backend` shows only the line that builds it) |

The outcome decides the answer: `STORED` and `STORED_NOT_BROADCAST` are the 200; `NO_ANCHOR` is a 400 `No earlier fix to anchor a no-fix frame to`; `UNKNOWN_DEVICE` is the 404 `Device not found or inactive` of today. With the hardware plan merged the handler may also return `ALERT_ONLY` (200) and may raise a store error, which the endpoint lets through as a 500, as today.

`msg_id` is random in `0..255` as today; `event_id` is new (the simulation had none) and is random in `0..65535`; `store_frame` does not consult the duplicate filter, so its value decides nothing.

**The falling edge at start.** `Simulation.start` already sends one frame in the past for every stale and lost persona. It also sends, for every SOS persona, one frame with `sos_active=False` at the start position before the loop begins; the loop's first SOS frame is then a rising edge on every start, whatever the previous run left in `location_events`. An alert of the previous run that is still **open** stays the open alert (`raise_sos` finds it and sends no message), so the manual check expects a new banner after Stop and Start only when the old alert was resolved first. The `mgrs` in the endpoint's answer is the one the parser computes for the frame (the same library call on the same latitude and longitude), so the existing assertion on it in `test_api_simulate.py` holds; for a no-fix frame the parser's `mgrs` is `''` and the endpoint still answers the MGRS of the passed latitude and longitude, so the test that compares the answer with the stored row uses a frame with a fix.

`insert_simulated_position` and `open_simulated_alert` and their repository functions are deleted with their tests. `simulation.reset` keeps calling `tracking_api.delete_positions_of_devices` and `sos_api.delete_alerts_of_devices`: deleting demo data is not feeding a frame and has no place in `gateway`.

### 1.3 Allowlist arithmetic (rows counted with the command of section 2)

| Entries today | What happens | Task |
|---------------|--------------|------|
| `sql_writes`: `main.py`, `location_events`, `DELETE` | deleted | T620 |
| `module_edges`: `backend.routers.test` to `tracking.api` and to `sos.api` (`until: 3`), with their two approvals | deleted: the router imports `gateway.api` only (an allowed edge of `simulation`) | T621 |
| `module_edges`: `backend.simulation` to `tracking.api` and to `sos.api` (`until: 3`), with their two approvals | replaced by the same two rows with `until: 5` and two new approvals (reason: "the reset of the demo data deletes positions and alerts through the two APIs until simulation becomes a module in step 5") | T621 |

In `approved_additions.py` that is four approvals deleted and two added. After T621 no row says `until: 3`, which T690 needs before it records step 3.

## 2. File map and who else touches each file (as of `d174ce3`)

Commands used: `git grep -nE "_cleanup_old_locations|Location cleanup|cleanup_task|from_fire_api" -- backend`; `git grep -nE "record_position|insert_simulated_position|open_simulated_alert|tracking_api\.location_update_payload" -- backend tools frontend/src`; the allowlist rows: `.venv\Scripts\python -c "import json;d=json.load(open('backend/tests/architecture/allowlist.json'));print([r for r in d['module_edges'] if r['until']==3]);print([r for r in d['sql_writes'] if r['file']=='main.py'])"`.

| File | This plan | Also read or written by |
|------|-----------|-------------------------|
| `backend/main.py` (hot) | T620 (`_cleanup_old_locations`, `cleanup_task`, three fire imports) | gateway plan T602, T603 |
| `backend/modules/tracking/module.py`, `backend/modules/fire/module.py`, `fire/tasks.py` | T620 | none in this wave |
| `backend/modules/tracking/api.py`, `infrastructure/repository.py` | T620 (one function added), then T621 (one function leaves) | wave 2 T547 (**before T621**) |
| `backend/modules/sos/api.py`, `infrastructure/repository.py` | T621 (one function leaves) | wave 2 T547 |
| `backend/routers/test.py`, `backend/simulation.py` | T621 | wave 2 T547 (the payload call in `record_position`; **before T621**) |
| `backend/tests/architecture/importlinter.toml` (hot) | T620 (`backend.modules.tracking.tasks` joins the `forbidden_modules` of `boundary-tracking`) | gateway plan T602, T603 |
| `backend/tests/architecture/allowlist.json`, `approved_additions.py` (hot) | T620, T621 | none (T602 edits the TOML only) |
| `tools/smoke.py`, `backend/tests/test_smoke_script.py`, `docs/SMOKE.md` (hot) | T621 (step l; step e keeps passing) | gateway plan T602 (step k) |
| `backend/tests/test_fire_anonymise.py`, `test_fire_poller.py`, `backend/tests/modules/fire/test_fire_api.py`, `backend/tests/test_b93_lifespan_shutdown.py` | T620 (the edits of section 5) | none |
| `backend/tests/test_api_simulate.py`, `backend/tests/test_simulation.py` | T621 (the edits of section 5) | wave 2 T547 |

## 3. Task order, PRs, reviewers

| PR | Task | Content | Needs | Owner | Reviewers | Hardware |
|----|------|---------|-------|-------|-----------|----------|
| 1 | T620 | retention and the fire clean-up are module tasks | gateway plan T600 | implementer | breaker + security-reviewer (`main.py`, deletion of personal data) | safe |
| 2 | T621 | the simulation feeds the gateway | gateway plan T600 and T604; wave 2 T547; T620 (the same two tracking files) | implementer | breaker + security-reviewer (`routers/**`) | safe |

T620 shares `main.py` and the TOML with T602 and T603 (different blocks and different contracts; the later branch merges `upstream/develop`).

## 4. Risks, rollback, not verified

| Risk | Mitigation |
|------|------------|
| The clean-up is not started | manifest tests and the first-pass test of T620; smoke run (the backend starts with both tasks) |
| bee-dev's test mode breaks (its only data source) | smoke steps e and l before the PR; the manual check "start test mode in Settings, six trackers move, the SOS banner shows once, Resolve keeps it resolved, Stop and Start again shows the SOS again" in the PR body |
| A `db`-marked test is skipped locally, so the DoD is green on the laptop and red in CI | section 5 lists the edits of the `db`-marked cases of `test_simulation.py`; the PR is not opened before its CI run is green |
| A tester relies on the simulated SOS coming back after Resolve inside one run | stated in the PR and in the overview; it now behaves like a real device |
| `recorded_at` loses its fraction of a second in simulated rows | stated; the frame format has whole seconds |

**Rollback.** No schema or data change. `git revert -m 1 <merge>` of T621, then of T620; T621 must be reverted before T604.

**Not verified while planning:** nothing was run; the `db`-marked tests were read, not executed.

## 5. Existing tests

| File | Edit | Kind | Task |
|------|------|------|------|
| `backend/tests/modules/fire/test_fire_api.py` (`test_fire_tasks_are_in_the_manifest`) and `backend/tests/modules/fire/test_fire_module.py` (the assertion marked `T503`) | both expect the fire task names `['poll_feeds', 'alarm_loop']`; they expect `['poll_feeds', 'alarm_loop', 'cleanup_fire_data']`. T620's own `test_the_fire_manifest_lists_the_cleanup_task_last` is then redundant and is dropped | deliberate: one task is added | T620 |
| `backend/tests/modules/fire/test_fire_api.py` (`test_main_names_no_fire_internals`) | its last assertion counts the `from .modules.fire.api import` lines of `main.py` and expects 1; T620 deletes that import, so it expects 0 | deliberate | T620 |
| the same file (the lifespan fixture) and `backend/tests/test_b93_lifespan_shutdown.py` | `monkeypatch.setattr(main, '_cleanup_old_locations', _park)` goes. In `test_fire_api.py` it is replaced by `monkeypatch.setattr(periodic, 'run_periodic', _park_any)` with `async def _park_any(*args, **kwargs)` (the existing `_park` takes no argument and would raise inside each task). In `test_b93` the module list is replaced by a probe, so the line is simply deleted | patch target | T620 |
| `backend/tests/test_fire_anonymise.py`, `backend/tests/test_fire_poller.py` (the cases that call `main._cleanup_old_locations()`) | these cases drive the endless loop with a fake `asyncio.sleep` that cancels after the second sleep, inside `pytest.raises(asyncio.CancelledError)`, and patch `main.get_pool`, `main.anonymise_alerts`, `main.anonymise_hotspots`, `main.prune_fire_data`. The `_once` functions do not sleep and do not loop, so the fake sleep and the `raises` block go; each case awaits `tracking.tasks.cleanup_positions_once()` and then `fire.tasks.cleanup_fire_data_once()` and patches the same names where the two task modules look them up. Every assertion on a log line, a count or the order `['location', 'fire']` stays | scaffolding and patch target; assertions unchanged | T620 |
| `backend/tests/test_smoke_script.py` (`test_test_endpoint_and_ws_message_shape_match_the_checks`) | it asserts that `routers/test.py` contains `tracking_api.location_update_payload(`; after T621 the router builds no payload, so the assertion reads the place the message is built for a simulated frame (the handler in `backend/modules/gateway/infrastructure/reader.py`) | deliberate: the code it reads moved | T621 |
| `backend/tests/test_api_simulate.py` | the cases that feed `mock_conn` answers in call order are rewritten on `gateway_fakes.install` (answers routed by SQL text); the assertions on status code and on `lat`, `lon`, `mgrs` stay; an assertion on `inserted` follows section 1.2 | deliberate: the statements behind the endpoint change | T621 |
| `backend/tests/test_simulation.py` (`db`-marked) | `test_reset_clears_demo_positions_and_alerts_only` calls `record_position` with a device row of `id` and `user_id` only: the row it builds gets `dev_sn`, `device_type` and `user_active`. `test_running_simulation_writes_positions_and_sos` counts rows: its counts are re-read against section 1.2 (one more position row per SOS persona at start; one alert per SOS persona, as before) and corrected only where that explains the difference | deliberate; a difference section 1.2 does not explain is a finding | T621 |
| tests of `insert_simulated_position` and `open_simulated_alert` in `backend/tests/modules/tracking/test_tracking_api.py` and `backend/tests/modules/sos/test_sos_api_commands.py` | deleted with the functions | deliberate | T621 |

## 6. Not done on purpose, and open questions

- `fire` still reads `location_events` through its own `reads_tables` and not through a `tracking.api.latest_positions` read model (modular-monolith.md 5.1, rule 6). It is legal today and it sits on the fire alarm path (BP-02); recommended for step 4 together with the read models of `people` and `devices`.
- The default admin (`main._ensure_default_admin`) stays in `main.py` until step 4 (`identity`), as the spec says.
- **To the maintainer:** T620 brings the retention move forward to step 3, as the spec's section 6 says; wave 2 asked to confirm that it waits for step 5 (overview of wave 2, item 9). Default of this plan: do it now.
- **To the architecture owner:** `simulation` keeps two edges to `tracking.api` and `sos.api` for its reset until step 5; text proposal for modular-monolith.md 4.2 in the overview.

---

### Task 620: retention and the fire clean-up become module tasks

**risk:** security
**owner:** implementer
**hardware:** safe
**Files:**
- Create: `backend/core/periodic.py`, `backend/modules/tracking/tasks.py`
- Modify: `backend/modules/tracking/module.py` (`tasks`), `backend/modules/tracking/api.py`, `infrastructure/repository.py`, `backend/modules/fire/tasks.py`, `backend/modules/fire/module.py` (`tasks`)
- Modify: `backend/main.py` (`_cleanup_old_locations`, `cleanup_task` and its `cancel()`, the import of `anonymise_alerts`, `anonymise_hotspots`, `prune_fire_data` go)
- Modify: `backend/tests/architecture/importlinter.toml` (`boundary-tracking` gets `backend.modules.tracking.tasks`), `allowlist.json` (one `sql_writes` row), the tests of section 5
- Create: `backend/tests/modules/core/test_periodic.py`, `backend/tests/modules/tracking/test_retention_task.py`, `backend/tests/modules/fire/test_fire_cleanup_task.py`

**Interfaces:**
- Produces `core/periodic.py`: `async def run_periodic(job: Callable[[], Awaitable[None]], *, first_delay: float = 30, period: float = 86_400) -> None` (sleeps `first_delay`, awaits `job()`, then sleeps `period` between passes for ever; an exception of `job` is logged as `'%s failed: %s'` with the job's `__name__` and the loop goes on; `asyncio.CancelledError` is not caught).
- Produces `tracking`: `repository.delete_positions_older_than(conn, days: int) -> int` (today's `WITH d AS (DELETE ...) SELECT COUNT(*)`, parameter `str(days)`, unchanged) and the pass-through `api.delete_positions_older_than`; `tasks.cleanup_positions_once() -> None` (acquires a pooled connection, deletes, logs the two lines of section 1.1 with `settings.location_retention_days`), `tasks.cleanup_positions() -> None` (`await periodic.run_periodic(cleanup_positions_once)`).
- Produces `fire.tasks`: `cleanup_fire_data_once() -> None` (the three blocks of today's loop, each with its own pooled connection, `try` and log lines) and `cleanup_fire_data() -> None`; the manifest's `tasks` is `(tasks.poll_feeds, tasks.alarm_loop, tasks.cleanup_fire_data)`.
- Produces in `main.py`: `lifespan` creates `notify_task` and the module tasks only.

- [ ] **Step 1: Write the failing tests**, tagged `T620`. `test_periodic.py` (with a fake `asyncio.sleep`): `test_the_first_pass_runs_after_30_seconds_and_the_next_after_a_day` (the recorded sleeps are `[30, 86_400]` after two passes); `test_a_failing_job_is_logged_and_the_loop_goes_on`; `test_cancelling_stops_the_loop`. `test_retention_task.py`: `test_the_delete_statement_and_its_argument_are_todays` (the mocked `conn.fetchval` got a text containing `DELETE FROM location_events` and `recorded_at < NOW() - ($1 || ' days')::interval`, and `str(settings.location_retention_days)`); `test_the_pass_logs_the_count_and_the_days`; `test_a_failed_delete_is_logged_and_does_not_raise`; `test_the_manifest_lists_the_retention_task` (`tracking_manifest.tasks == (tasks.cleanup_positions,)`); `test_main_holds_no_cleanup` (the text of `backend/main.py` has none of `_cleanup_old_locations`, `location_events`, `anonymise_`, `prune_fire_data`); `test_the_manifest_task_runs_its_first_pass_after_30_seconds` (`start_module_tasks([tracking_manifest], ...)` with the real `run_periodic` and a fake `asyncio.sleep`: the recorded first sleep is 30 and the log line `Location cleanup: removed` follows it); `test_both_cleanups_are_started_by_the_module_list` (`start_module_tasks(MODULES, ...)` with `periodic.run_periodic` patched by a recorder that accepts any arguments records two calls, one per `_once` function). `test_fire_cleanup_task.py`: `test_the_three_fire_jobs_run_even_when_the_first_fails`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\core\test_periodic.py backend\tests\modules\tracking\test_retention_task.py backend\tests\modules\fire\test_fire_cleanup_task.py -q`. Expected: FAIL with `ModuleNotFoundError: No module named 'backend.core.periodic'`.
- [ ] **Step 3: Move** the four blocks, write the helper and the two manifest fields, add the TOML line, delete the loop from `main.py`, apply the test edits of section 5.
- [ ] **Step 4: Shrink the allowlist.** Run: `cd bee-with-me; .venv\Scripts\python backend\tests\architecture\regen.py --check`. Expected: `allowlist.json: 1` (the `main.py` row). Then `--remove-stale`, then `.venv\Scripts\python -m pytest backend\tests\architecture -q`. Expected: PASS.
- [ ] **Step 5: Run** the DoD list, then `python tools/smoke.py`. Expected: PASS and every smoke step PASS (the backend starts with the two new tasks); the retention and anonymisation assertions of `test_fire_anonymise.py` and `test_fire_poller.py` are unchanged.
- [ ] **Step 6: Commit** `refactor(tracking): T620 retention and the fire clean-up are module tasks`. PR body: the four jobs before and after, the unchanged log lines, the DP-03 note (each job still fails alone and loudly).

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_fire_anonymise.py backend\tests\test_fire_poller.py backend\tests\test_b93_lifespan_shutdown.py backend\tests\test_b49.py backend\tests\test_startup_migrations.py -q`

### Task 621: the simulation feeds the gateway

**risk:** security
**owner:** implementer
**hardware:** safe (no pinned function and no handler is edited)
**Files:**
- Modify: `backend/routers/test.py` (`simulate`, `record_position`), `backend/simulation.py` (`seed`: the three statements that return a device row return the columns of section 1.2; `Simulation.start`: the falling-edge frame)
- Modify: `backend/modules/tracking/api.py`, `infrastructure/repository.py` (`insert_simulated_position` goes), `backend/modules/sos/api.py`, `infrastructure/repository.py` (`open_simulated_alert` goes)
- Modify: `backend/tests/architecture/allowlist.json`, `approved_additions.py`
- Modify: `tools/smoke.py`, `backend/tests/test_smoke_script.py`, `docs/SMOKE.md` (step l)
- Modify: the tests of section 5
- Create: `backend/tests/modules/gateway/test_simulation_through_gateway.py`

**Interfaces:**
- Consumes: `gateway.api.encode_bee_frame`, `gateway.api.parse_frame`, `gateway.api.store_frame`, `gateway.api.Outcome` (T604).
- Produces in `routers/test.py`: `record_position(conn, device, lat, lon, sos_active, *, gnss_valid=True, battery=None, at=None) -> dict` keeps its name and parameters; `device` carries `id`, `user_id`, `dev_sn`, `device_type` and `user_active`. It works as the right column of section 1.2, sends `course_deg=0` (a latitude the MGRS conversion refuses makes `parse_frame` raise, and an unparsable frame returns `None`: the endpoint lets the raise through as today's 500 for such a request and answers 400 `Frame could not be built` for `None`), and returns `{'inserted': True, 'lat': lat, 'lon': lon, 'mgrs': <MGRS of lat, lon>}`. Its answers: 400 `User is inactive` (text unchanged), 400 `Device is not a bee`, 400 `No earlier fix to anchor a no-fix frame to`, 404 `Device not found or inactive`. The router imports `gateway.api` and neither `tracking.api` nor `sos.api`.
- Produces in `simulation.py`: `seed` rows with the five columns; `Simulation.start` sends the frame without SOS for every SOS persona before it creates the loop task.
- Produces in `allowlist.json` and `approved_additions.py`: the rows and approvals of section 1.3.
- Produces in `tools/smoke.py`: step `'l. simulated SOS reaches /ws and the alert list'`, `needs=('c. admin login + token refresh',)`: creates a person and a bee as step e does, opens `/ws`, posts `/api/test/simulate` with `sos_active: true`, expects one message with `type == 'sos_alert'` and that device's `device_id`, then `GET /api/locations/sos` lists an alert of that device.

- [ ] **Step 1: Write the failing tests**, tagged `T621`, in `test_simulation_through_gateway.py` (the fakes of `gateway_fakes.py`): `test_simulate_stores_through_the_gateway_handler` (`gateway.api.store_frame` is awaited once with a `BeeFrame` whose `dev_sn`, position, battery and SOS flag are the request's); `test_a_past_contact_time_is_stored_as_received_at` (`at` two hours ago: the handler's `received_at` argument is exactly `at` and the frame's `recorded_at` is `at` cut to the second); `test_a_simulated_sos_sends_sos_alert_once_and_not_again_on_the_next_frame`; `test_a_resolved_simulated_alert_is_not_reopened_by_the_next_frame`; `test_a_second_start_without_a_reset_raises_the_alarm_again` (`Simulation.start` awaits `record_position` with `sos_active=False` for each SOS persona before the loop; with the fakes' previous flag true, the loop's first SOS frame opens an alert); `test_an_inactive_person_is_a_400_and_nothing_is_stored`; `test_a_repeater_is_a_400`; `test_a_no_fix_frame_without_an_earlier_fix_is_a_400`; `test_an_unknown_device_outcome_is_a_404`; `test_the_live_message_has_course_deg`; `test_seed_rows_can_be_recorded` (a row with the five columns `seed` returns goes through `record_position` without a `KeyError`; a source check that each of `seed`'s three `RETURNING` or `SELECT` clauses names `dev_sn`, `device_type` and `user_active`); `test_the_router_imports_gateway_api_and_no_tracking_or_sos_api` (the import graph of `backend.routers.test`); `test_the_simulated_writers_are_gone` (`tracking.api` has no `insert_simulated_position`, `sos.api` no `open_simulated_alert`). In `test_smoke_script.py`: `test_sos_frame_step_passes_when_the_message_and_the_alert_arrive`, `test_sos_frame_step_fails_without_the_message`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\gateway\test_simulation_through_gateway.py -q`. Expected: FAIL (`store_frame` is not awaited; `insert_simulated_position` still exists).
- [ ] **Step 3: Implement** the router and the two `simulation.py` edits, delete the two simulated writers, add the smoke step, apply the test edits of section 5.
- [ ] **Step 4: Shrink and carry the allowlist.** `regen.py --check` (expected: `allowlist.json: 2`, the two `backend.routers.test` rows; the two `backend.simulation` rows are live because of the reset), `--remove-stale`, then change `until` of the two `backend.simulation` rows to 5 by hand, delete the four old approvals, add the two new ones, and run `.venv\Scripts\python -m pytest backend\tests\architecture -q`. Expected: PASS; no row has `until: 3`.
- [ ] **Step 5: Run** the DoD list, then `python tools/smoke.py`. Expected: PASS; smoke steps e, j, k and l PASS. The `db`-marked cases of `test_simulation.py` are skipped without a database: the branch is pushed and its CI run must be green before the PR is opened.
- [ ] **Step 6: Commit** `refactor(simulation): T621 simulated frames go through gateway.api`. PR body: the table of section 1.2 (every row is a behaviour difference of test mode), the manual check of section 4, the allowlist arithmetic.

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_api_simulate.py backend\tests\test_simulation.py backend\tests\test_smoke_script.py backend\tests\test_parser.py -q`
