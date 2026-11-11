# Vertical slices, step 3: the hardware path fix (ACK after store, one transaction, no ACK for an unknown device) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the gateway acknowledge a frame only when it is stored: a frame is marked as seen after the store, a failed store sends no ACK, an unknown device gets no ACK, and position, SOS and both notifications are one transaction (R-06, R-07, ES-23, modular-monolith.md 5.1).

**Architecture:** The handlers return an outcome, a pure table in the gateway's `domain/` says for each outcome whether it is acknowledged and whether it marks the event as seen, and `_process_frame` only asks the table. The outcome table is merged first and alone (pure, unused, reviewable by the device maker as a table); the three tasks that wire it change the duplicate filter and the ACK and are merged only after Kiril Penev has run them on a real gateway with the protocol of section 2.

**Tech Stack:** Python 3.11+, asyncpg, pytest. No new dependency, no migration.

**Spec:** [`docs/superpowers/specs/2026-10-31-vertical-slices-programme-design.md`](../specs/2026-10-31-vertical-slices-programme-design.md) sections 2 (anti-goals), 5 ("Step 3"), 6 ("Hardware path"), 9 question 2; `Architecture/application/modular-monolith.md` 5.1 and 10; `Architecture/governance/risk-register.md` R-06, R-07; `docs/PROTOCOL.md` section "Cmd=1" (it already states the intended rule: the ACK follows a successful store). Overview: [`2026-11-11-vs-wave3-overview.md`](2026-11-11-vs-wave3-overview.md).

**Base:** `upstream/develop` at `d174ce3`, plus the gateway plan (T601 to T604) merged. Execution branches: `feature/vs-3-<task>`.

## Global Constraints

- The decisions of the gateway plan's Global Constraints apply. Tags: `T61x`.
- **Hardware rule.** T611, T612 and T613 edit the duplicate filter and the ACK. Each is merged **only after** Kiril Penev has run its branch against a real gateway and real devices with the steps of section 2 and the filled result table is in the PR body. The agent never runs anything against a gateway or a field machine. T610 is pure and unused and is safe without hardware.
- Each of T611 to T613 changes a function pinned by T601 and therefore updates the literal of `hid_reader._process_frame` in `frozen_hashes.py` in the same commit (regenerated with `.venv\Scripts\python backend\tests\modules\gateway\frozen_hashes.py`, never typed). No other pinned name may change: the parser, `_send_data`, `run`, `EVENT_TIMEOUT` and `HID_BUFFER_SIZE` are not touched by this plan.
- The fast path stays direct: no queue, no dispatcher, no second connection. The transaction of T613 is opened by the gateway handler on the reader's own connection; `tracking.api` and `sos.api` still open none.
- `docs/PROTOCOL.md` is not edited (owner-written). The texts it needs are proposals in the overview.
- No store timeout is added in this plan: a database that hangs (not fails) blocks the reader as it does today. Whether to add one depends on the device's ACK deadline (overview, question to the device maker).

## Review Focus

1. A frame is acknowledged although nothing was stored (the anti-goal of the spec): every path of `_process_frame` that returns a confirm is behind `should_ack(outcome)`, and the three former `xfail` tests run as ordinary tests (T611, T612, T613).
2. A frame that was stored is stored again when its ACK was lost: the retransmission (same `EventID` inside the window) is a `DUPLICATE`, is not stored and **is** acknowledged (`a retransmission of a stored frame is acked and not stored twice`, T611).
3. A device that is never acknowledged retransmits for ever and drains its battery or the radio channel: the number and spacing of retransmissions is measured in V2 and reported before T612 is merged; the policy is one table (T610), so the answer changes one line.
4. A store that fails between the position and the SOS leaves a position with `sos_active` and no alert: one transaction, rolled back as a whole (T613, `a failure after the position insert leaves no row and no notification`).
5. The connection is dead and the reader keeps swallowing errors: a closed connection is re-raised so `run` reconnects (T611, `a closed connection is not swallowed`).

---

## 1. Design

### 1.1 Outcomes and the policy table (T610)

| Outcome | When | ACK | Marks the event as seen | Today |
|---------|------|-----|-------------------------|-------|
| `STORED` | the position or heartbeat is committed | yes | yes | ACK, seen **before** the store |
| `STORED_NOT_BROADCAST` | stored; the person is inactive, so no live message | yes | yes | the same |
| `DUPLICATE` | same `EventID` for the device inside `EVENT_TIMEOUT` | yes | (already) | the same |
| `NO_ANCHOR` | a no-fix frame from a known device with no earlier fix; dropped by design (PROTOCOL.md) | yes | yes | the same |
| `UNKNOWN_DEVICE` | no active device row for the serial number and type | **no** | **no** | ACK, seen |
| `STORE_FAILED` | the store raised | **no** | **no** | the error tears the reader down; the event stays seen, so the retransmission is dropped **and acknowledged** (R-06) |
| `UNPARSEABLE` | `parse_frame` returned nothing | no | no | the same |

`NO_ANCHOR` is acknowledged because the device is known and a retransmission cannot change the result; `UNKNOWN_DEVICE` is not, so that the frame arrives again once an admin has registered the device (spec, section 5). Both lines are the default of this plan and the subject of a question to the owner and the device maker (overview, section 7); a different answer is a one-line change of the table and of its test.

A handler result that is not an `Outcome` (for example `None` from a mocked handler in an existing test) counts as `STORED`, so the unedited characterisation tests of `test_hid_process_frame.py`, which patch the handlers with mocks, keep their meaning.

### 1.2 The new shape of `_process_frame` (T611, T612)

```
frame = parse_frame(raw)                      -> None: return None (UNPARSEABLE)
if (dev_sn, event_id) seen inside the window  -> outcome = DUPLICATE
else:
    try:    outcome = await handler(frame, conn)
    except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError) as exc:
            log WARNING 'Frame not stored, no ACK sent: dev_sn=%s event_id=%s reason=%s' (reason through core.database.redact)
            if conn.is_closed(): raise        (run() reconnects, as today)
            outcome = STORE_FAILED
    if marks_seen(outcome): remember (event_id, now) for the device
return make_confirm(frame.msg_id) if should_ack(outcome) else None
```

Bees and repeaters keep their two dictionaries and the 15 second window. An outcome that is not acknowledged is logged once at INFO: `'No ACK for dev_sn=%s event_id=%s: %s'` with the outcome's value. The existing lines `HID frame extracted:` and `HID confirm to send:` stay; together they let the validation read every ACK decision from the backend log.

### 1.3 One transaction (T613)

`_handle_bee` keeps its order of work. The device check and the no-anchor check stay outside (they store nothing). From `previous_sos_flag` to `publish_position` everything runs inside `async with conn.transaction():`, so the `INSERT` of the position, the `INSERT` of the alert and both `pg_notify` calls commit together and the notifications are delivered after the commit (ADR 7). `_handle_repeater` wraps its single `INSERT` the same way. The ACK is built by `_process_frame` after the handler returned, that is after the commit. The simulation gets the same transaction through `gateway.api.store_frame`.

## 2. Validation on a real gateway (run by Kiril Penev; the result table goes into each PR body)

**Bench.** A machine with the USB gateway, the database container of `docker/docker-compose.yaml` running (`podman ps` or `docker ps` shows its name), the backend started from the task's branch with `start.ps1` or `start.sh`, `ENABLE_TEST_ENDPOINTS` not set. One bee registered in the Devices page with its real `DevSN` (device A), one bee that is **not** registered (device B). The backend log is kept for the whole run. Rows are counted with `podman exec <db container> psql -U <user> -d <database> -c "SELECT count(*), max(received_at) FROM location_events WHERE device_id = '<id of A>'"` (Docker: the same with `docker exec`). Never run this on a machine that holds operation data.

| Check | For | Steps | Expected |
|-------|-----|-------|----------|
| V0 start | T602, T603 (release gate), repeated before every other check | start the backend with the gateway plugged in; let A transmit twice | log: `HID device opened VID=... PID=...`; `GET /api/serial/status` shows `connected: true` and `frames_received` climbing; A is on the map; each frame has one `HID confirm to send:` line; the row count grows by one per frame |
| V1 failed store | T611 | while A transmits, stop the database container (`podman stop <db container>`), wait for at least two transmissions of A, start it again | during the outage: no `HID confirm to send:` line; a line `Frame not stored, no ACK sent` or the reader's reconnect lines; A retransmits (seen on the device or the gateway). After the start: the reader reconnects by itself, the retransmitted frame is stored **once** and acknowledged; no frame of A that the device still held is missing from `location_events` |
| V1b slow store | T611 (observe, no pass or fail) | `podman pause <db container>` for 20 seconds, then `podman unpause` | write down: does A retransmit while the store hangs, and are the copies that arrive after the unpause acknowledged without a second row (they are `DUPLICATE`)? The answer decides whether a store timeout is needed |
| V2 unknown device | T612 | let B transmit for five minutes; then register B in the Devices page | before: log `Unknown or inactive bee dev_sn=<B>`, a line `No ACK for dev_sn=<B>`, no `HID confirm to send:` for B's `MsgId`; write down **how many times and how often B retransmits one frame and when it gives up**. After registering: the next frame of B is stored, acknowledged and on the map |
| V3 lost ACK | T611 | unplug the gateway's USB cable right after A transmits and plug it in again inside 15 seconds (or any other way the device maker has to drop one ACK) | the retransmitted frame is logged `Repeated BeeFrame ignored`, is acknowledged, and the row count grew by one, not two |
| V4 SOS in one transaction | T613 | in a second terminal `psql ... -c "LISTEN sos_alert; LISTEN location_update;"` kept open; press SOS on A; resolve the alert in the banner; let A send two more frames with SOS still asserted | one `sos_alerts` row and one `location_events` row for the press; both notifications arrive together and the rows are already visible to a `SELECT` at that moment; the banner shows once; the two later frames open no new alert; every frame has its ACK |
| V5 soak | T611 to T613 together, before the release | A and at least one more registered bee and one repeater transmit for 30 minutes | the number of `HID frame extracted:` lines that parse equals the number of `HID confirm to send:` lines plus the `No ACK` lines; the row counts of `location_events` and `repeater_events` equal the acknowledged non-duplicate frames; no `Frame not stored` line |

**Result table for the PR body** (one line per check): check, date, firmware version of the devices, PASS or FAIL, the numbers written down (V1b, V2), who ran it. A FAIL stops the merge and becomes a `B<n>` entry.

## 3. Task order, PRs, reviewers

| PR | Task | Content | Needs | Owner | Reviewers | Hardware |
|----|------|---------|-------|-------|-----------|----------|
| 1 | T610 | outcomes and the ACK policy table (pure, unused) | gateway plan T602 | implementer | breaker | **safe**: merge at once |
| 2 | T611 | seen after the store; a failed store is not acknowledged | T610, T604 | implementer | breaker + security-reviewer (`hardware_reader/**`) | **waits**: V0, V1, V1b, V3 |
| 3 | T612 | no ACK for an unknown or inactive device | T611; the answer to the policy question | implementer | breaker + security-reviewer | **waits**: V0, V2 |
| 4 | T613 | position, SOS and notifications in one transaction | T612 | implementer | breaker + security-reviewer | **waits**: V0, V4, then V5 on the sum |

The three waiting tasks are a strict chain (all edit `_process_frame` or `_handle_bee`). They may be **implemented and reviewed** as soon as T610 is merged; only the merge waits. If the bench is available for one session only, the three branches are stacked (`feature/vs-3-t612` off `feature/vs-3-t611`) and validated in order V0, V1, V1b, V3, V2, V4, V5 in that session, and merged in order afterwards.

**PR gate:** the gate of the gateway plan, plus the result table of section 2, plus the hardware note: "This PR changes the duplicate filter and the ACK. Validated on a real gateway by Kiril Penev on <date>, checks <list>: results below. Not run against hardware by the agent."

## 4. Risks, rollback, not verified

| Risk | Mitigation |
|------|------------|
| The device retransmits an unacknowledged frame without limit | measured in V2 before T612 is merged; the policy is one line of the table |
| The commit makes the ACK later than the device's deadline, so stored frames are retransmitted | the copies are `DUPLICATE`: acknowledged, not stored twice (V1b, V3); the deadline is asked from the device maker |
| An error type that is not caught escapes `_process_frame` | it reaches `run`'s `except Exception`, which reconnects as today; the event is not marked seen because marking happens after the handler |
| The first frame after a restart is a retransmission of a frame stored before the restart | the window dictionary is empty after a restart, so the frame is stored twice (two rows, same `recorded_at`). This exists today; it is stated, not fixed (a fix needs `EventID` in `location_events`, a migration, step 4 or later) |
| The simulation's SOS behaves differently inside the transaction | `store_frame` runs the same handler; smoke steps e and l (tracking plan) cover it without hardware |

**Rollback.** No schema or data change. Revert newest first: T613, T612, T611; each revert restores the matching `FROZEN` literal because it is in the same commit. T610 may stay.

**Not verified while planning:** the device's retry count, retry interval and ACK deadline (unknown, asked); whether `asyncpg` raises `PostgresError`, `InterfaceError` or `OSError` when the container stops mid-statement (all three are caught; V1 shows which); nothing was run on hardware.

## 5. Existing tests

| File | Edit | Kind | Task |
|------|------|------|------|
| `backend/tests/modules/gateway/test_hid_process_frame.py` | the `xfail` marker of `test_failed_store_does_not_mark_the_event_seen` is removed | deliberate: the debt it names is paid | T611 |
| the same file | the `xfail` marker of `test_unknown_device_frame_is_not_acked` is removed | deliberate | T612 |
| the same file | the `xfail` marker of `test_bee_frame_is_stored_in_one_transaction` is removed | deliberate | T613 |
| `backend/tests/modules/gateway/frozen_hashes.py` | the literal of `hid_reader._process_frame` | deliberate, regenerated | T611, T612 |

The bodies of the three tests are not edited: they were written against the intended behaviour. Every other test of `backend/tests/modules/gateway/` stays unedited; a characterisation test that fails is a finding, not something to adapt.

## 6. Open questions (details in the overview, section 7)

1. **To the device maker:** retry count, retry interval and ACK deadline of a bee and a repeater; is there a negative acknowledgement; does `EventID` restart after a device reboot.
2. **To the owner and the device maker:** the two policy lines `NO_ANCHOR` (ACK) and `UNKNOWN_DEVICE` (no ACK).
3. **To the owner:** who runs section 2, on which gateway, in which window (spec section 9, question 2).

---

### Task 610: outcomes and the ACK policy table

**risk:** normal
**owner:** implementer
**hardware:** safe (pure, not imported by the reader yet)
**Files:**
- Create: `backend/modules/gateway/domain/outcome.py`, `backend/tests/modules/gateway/test_outcome.py`

**Interfaces:**
- Produces: `class Outcome(str, enum.Enum)` with the members `STORED = 'stored'`, `STORED_NOT_BROADCAST = 'stored_not_broadcast'`, `DUPLICATE = 'duplicate'`, `NO_ANCHOR = 'no_anchor'`, `UNKNOWN_DEVICE = 'unknown_device'`, `STORE_FAILED = 'store_failed'`, `UNPARSEABLE = 'unparseable'`; `ACK_POLICY: dict[Outcome, bool]` and `SEEN_POLICY: dict[Outcome, bool]` with the values of section 1.1; `should_ack(outcome: object) -> bool` and `marks_seen(outcome: object) -> bool`, both returning `True` for a value that is not an `Outcome`.

- [ ] **Step 1: Write the failing tests**, tagged `T610`: `test_the_policy_is_the_table_of_the_plan` (two literal dictionaries equal `ACK_POLICY` and `SEEN_POLICY`); `test_every_outcome_has_both_policies`; `test_nothing_unstored_is_acknowledged_except_a_duplicate_and_a_no_anchor_frame` (for every outcome with `ACK_POLICY` true, the outcome is one of `STORED`, `STORED_NOT_BROADCAST`, `DUPLICATE`, `NO_ANCHOR`); `test_a_handler_result_that_is_no_outcome_counts_as_stored` (`None` and `object()`); `test_the_module_is_pure` (its source imports only `enum` and `__future__`).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\gateway\test_outcome.py -q`. Expected: FAIL with `ModuleNotFoundError: No module named 'backend.modules.gateway.domain.outcome'`.
- [ ] **Step 3: Implement** the file.
- [ ] **Step 4: Run.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\gateway backend\tests\architecture -q`. Expected: PASS (`domain is pure` included; T601 hashes untouched).
- [ ] **Step 5: Commit** `feat(gateway): T610 frame outcomes and the ACK policy table`. PR body: the table of section 1.1, addressed to the owner and the device maker for a yes or a correction.

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\gateway backend\tests\architecture -q`

### Task 611: a frame is marked as seen after the store, and a failed store is not acknowledged

**risk:** security
**owner:** implementer
**hardware:** **waits for hardware.** Merged only after Kiril Penev ran V0, V1, V1b and V3 of section 2 on this branch; the result table is in the PR body.
**Files:**
- Modify: `backend/modules/gateway/infrastructure/hid_reader.py` (`_process_frame` only), `backend/modules/gateway/infrastructure/reader.py` (`_handle_bee`, `_handle_repeater`: return values only)
- Modify: `backend/tests/modules/gateway/test_hid_process_frame.py` (one marker), `frozen_hashes.py` (one literal)
- Create: `backend/tests/modules/gateway/test_ack_after_store.py`

**Interfaces:**
- Consumes: T610 (`Outcome`, `marks_seen`); T604.
- Produces in `reader.py`: `_handle_bee` returns `Outcome.UNKNOWN_DEVICE` (no device row), `Outcome.NO_ANCHOR` (no-fix frame without an earlier fix), `Outcome.STORED_NOT_BROADCAST` (inactive person) or `Outcome.STORED`; `_handle_repeater` returns `Outcome.UNKNOWN_DEVICE` or `Outcome.STORED`. No statement, log line or order changes.
- Produces in `hid_reader.py`: `_process_frame` has the shape of section 1.2 with one difference kept for T612: it still acknowledges every outcome except `STORE_FAILED` (so `UNKNOWN_DEVICE` is acknowledged and marked seen as today). The store error is caught as written in section 1.2, logged with the redacted reason, re-raised when `conn.is_closed()`.

- [ ] **Step 1: Write the failing tests**, tagged `T611`, in `test_ack_after_store.py` (handlers patched as in `test_hid_process_frame.py`, the controlled clock of that file): `test_a_failed_store_sends_no_ack_and_the_retransmission_is_stored` (handler raises `asyncpg.PostgresError` once: result `None`, device not in `bee_last_events`; the second call awaits the handler again and returns the confirm); `test_a_retransmission_of_a_stored_frame_is_acked_and_not_stored_twice`; `test_a_failed_repeater_store_sends_no_ack`; `test_the_reason_is_logged_without_the_password` (the error text carries `password=secret`; the WARNING line has `dev_sn`, `event_id` and no `secret`); `test_a_closed_connection_is_not_swallowed` (`conn.is_closed()` true: the error propagates); `test_an_interface_error_and_an_os_error_are_store_failures`; `test_the_handlers_return_outcomes` (the fakes of `gateway_fakes.py`: unknown device, no anchor, inactive person, stored; repeater unknown and stored). Remove the `xfail` marker of `test_failed_store_does_not_mark_the_event_seen`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\gateway\test_ack_after_store.py backend\tests\modules\gateway\test_hid_process_frame.py -q`. Expected: FAIL (`1235` is in `bee_last_events` after the failed store; the handlers return `None`).
- [ ] **Step 3: Implement**, then regenerate the literal of `hid_reader._process_frame`.
- [ ] **Step 4: Run.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_parser.py -q`. Expected: PASS; two `xfail` tests are left; `test_decode_duplicate_filter_and_ack_are_unchanged` passes with exactly one changed literal (`git diff upstream/develop -- backend/tests/modules/gateway/frozen_hashes.py` shows one line).
- [ ] **Step 5: Hand over for validation.** Push the branch, write the PR body with the empty result table of section 2 (V0, V1, V1b, V3) and stop: the PR is opened by the human and merged only with the table filled.
- [ ] **Step 6: Commit** `fix(gateway): T611 a frame is marked seen after the store and a failed store gets no ACK`.

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_parser.py -q`

### Task 612: no ACK for an unknown or inactive device

**risk:** security
**owner:** implementer
**hardware:** **waits for hardware.** Merged only after V0 and V2 on this branch, and after the owner and the device maker have confirmed the policy table of T610 (the retransmission numbers of V2 are part of that answer).
**Files:**
- Modify: `backend/modules/gateway/infrastructure/hid_reader.py` (`_process_frame` only)
- Modify: `backend/tests/modules/gateway/test_hid_process_frame.py` (one marker), `frozen_hashes.py` (one literal)
- Create: `backend/tests/modules/gateway/test_ack_policy_wired.py`

**Interfaces:**
- Consumes: T610 (`should_ack`, `marks_seen`), T611.
- Produces in `hid_reader.py`: `_process_frame` returns the confirm only when `should_ack(outcome)` and remembers the event only when `marks_seen(outcome)`; an outcome that is not acknowledged is logged at INFO as `'No ACK for dev_sn=%s event_id=%s: %s'`.

- [ ] **Step 1: Write the failing tests**, tagged `T612`: `test_every_outcome_is_acked_exactly_as_the_table_says` (parametrised over `Outcome` without `DUPLICATE` and `UNPARSEABLE`: the handler returns the outcome; the result is a confirm or `None` as `ACK_POLICY` says, and the device is in the window dictionary as `SEEN_POLICY` says); `test_an_unknown_device_is_stored_and_acked_after_it_is_registered` (first frame: `UNKNOWN_DEVICE`, no ACK; the same frame again inside the window with the handler now returning `STORED`: handled and acknowledged); `test_a_no_anchor_frame_is_acked_and_not_handled_twice`; `test_the_refusal_is_logged_once_per_frame`; `test_a_mocked_handler_without_an_outcome_is_acked` (the unedited tests rely on it). Remove the `xfail` marker of `test_unknown_device_frame_is_not_acked`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\gateway\test_ack_policy_wired.py backend\tests\modules\gateway\test_hid_process_frame.py -q`. Expected: FAIL (an unknown device is acknowledged).
- [ ] **Step 3: Implement**, then regenerate the literal.
- [ ] **Step 4: Run.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_parser.py -q`. Expected: PASS; one `xfail` test is left.
- [ ] **Step 5: Hand over for validation** (V0, V2; the PR body has the numbers "retransmissions per frame", "interval", "gives up after").
- [ ] **Step 6: Commit** `fix(gateway): T612 an unknown or inactive device gets no ACK`.

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_parser.py -q`

### Task 613: position, SOS and notifications in one transaction

**risk:** security
**owner:** implementer
**hardware:** **waits for hardware.** Merged only after V0 and V4 on this branch; V5 is run on the sum of T611 to T613 before the release.
**Files:**
- Modify: `backend/modules/gateway/infrastructure/reader.py` (`_handle_bee`, `_handle_repeater`)
- Modify: `backend/tests/modules/gateway/test_hid_process_frame.py` (one marker)
- Create: `backend/tests/modules/gateway/test_one_transaction.py`

**Interfaces:**
- Consumes: T612; `gateway_fakes.GatewaySql.record_transactions`.
- Produces in `reader.py`: the transaction of section 1.3. `_handle_bee` opens no transaction for `UNKNOWN_DEVICE` and `NO_ANCHOR`. An exception inside the block leaves it (rollback) and reaches `_process_frame`, which turns it into `STORE_FAILED`. The statements, their texts and their order are unchanged; `hid_reader.py` is not edited, so no frozen literal changes.

- [ ] **Step 1: Write the failing tests**, tagged `T613`, in `test_one_transaction.py`: `test_a_failure_after_the_position_insert_leaves_no_row_and_no_notification` (the fake raises on `INSERT INTO sos_alerts`: the log has `('tx', 'begin')`, then `('tx', 'rollback')`, no `('tx', 'commit')`, and `_process_frame` returns `None`); `test_a_plain_position_is_one_transaction_with_its_notification_inside`; `test_an_inactive_person_is_stored_in_a_transaction_without_a_notification`; `test_an_unknown_device_opens_no_transaction`; `test_a_no_anchor_frame_opens_no_transaction`; `test_a_heartbeat_is_one_transaction`; `test_the_statements_and_their_order_are_unchanged` (the six literal lists of `test_reader_delegates.py` still match). If `record_transactions` does not log a rollback, extend the fake in `gateway_fakes.py` by that one entry and say so in the PR body. Remove the `xfail` marker of `test_bee_frame_is_stored_in_one_transaction`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\gateway\test_one_transaction.py backend\tests\modules\gateway\test_hid_process_frame.py -q`. Expected: FAIL (no `('tx', 'begin')` in the log).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the DoD and the smoke. Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_parser.py backend\tests\test_api_simulate.py backend\tests\test_simulation.py -q`. Expected: PASS; no `xfail` is left in `backend/tests/modules/gateway` (`git grep -n xfail backend/tests/modules/gateway` prints only the comment line of `gateway_fakes.py`). Then `python tools/smoke.py`: steps e and l PASS (the simulated frame and the simulated SOS go through the same transaction).
- [ ] **Step 5: Hand over for validation** (V0, V4; then V5 on the merged sum).
- [ ] **Step 6: Commit** `fix(gateway): T613 a frame is stored and announced in one transaction`.

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_parser.py backend\tests\test_api_simulate.py backend\tests\test_simulation.py -q`
