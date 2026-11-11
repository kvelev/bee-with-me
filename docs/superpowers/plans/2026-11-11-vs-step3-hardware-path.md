# Vertical slices, step 3: the hardware path fix (ACK after store, one transaction, no ACK for an unknown device) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the gateway acknowledge a frame only when it is stored: a frame is marked as seen after the store, a store that failed for a passing reason sends no ACK, an unknown device gets no ACK, and position, SOS and both notifications are one transaction (R-06, R-07, ES-23, modular-monolith.md 5.1).

**Architecture:** The handlers return an outcome (since T604 of the gateway plan), a pure table in the gateway's `domain/` says for each outcome whether it is acknowledged and whether it marks the event as seen, and `_process_frame` only asks the table. The outcome table is merged first and alone (pure, reviewable by the device maker as a table). The three tasks that wire it change the duplicate filter, the ACK and the store; they are validated together on a real gateway by Kiril Penev with the protocol of section 2 and are merged together.

**Tech Stack:** Python 3.11+, asyncpg, pytest. No new dependency, no migration.

**Spec:** [`docs/superpowers/specs/2026-10-31-vertical-slices-programme-design.md`](../specs/2026-10-31-vertical-slices-programme-design.md) sections 2 (anti-goals), 5 ("Step 3"), 6 ("Hardware path"), 9 question 2; `Architecture/application/modular-monolith.md` 5.1 and 10; `Architecture/governance/risk-register.md` R-06, R-07; `docs/PROTOCOL.md` section "Cmd=1" (it already states the intended rule: the ACK follows a successful store). Overview: [`2026-11-11-vs-wave3-overview.md`](2026-11-11-vs-wave3-overview.md).

**Base:** `upstream/develop` at `d174ce3`, plus the gateway plan (T601 to T604) merged. Execution branches: `feature/vs-3-<task>`.

## Global Constraints

- The decisions of the gateway plan's Global Constraints apply. Tags: `T61x`.
- **Hardware rule.** T611, T612 and T613 edit the duplicate filter, the ACK and the store of a frame. They are merged **only after** Kiril Penev has run their stacked branches against a real gateway and real devices with the steps of section 2 and the filled result table is in each PR body. The agent never runs anything against a gateway or a field machine. T610 is pure and is safe without hardware.
- **The three are one unit.** T611 without T613 is worse than today for one case (section 4, first row), so the three PRs are merged in order on the same day and no release is tagged between them.
- T611 and T612 change a function pinned by T601 and update the literal of `hid_reader._process_frame` in `frozen_hashes.py` in the same commit (regenerated with `.venv\Scripts\python backend\tests\modules\gateway\frozen_hashes.py`, never typed). No other pinned name may change: the parser, `_send_data`, `run`, the constants and the frame classes are not touched by this plan.
- The fast path stays direct: no queue, no dispatcher, no second connection. The transaction of T613 is opened by the gateway handler on the reader's own connection; `tracking.api` and `sos.api` still open none.
- `docs/PROTOCOL.md` is not edited (owner-written). The texts it needs are proposals in the overview.
- No store timeout is added in this plan: a database that hangs (not fails) blocks the reader, and with it every other device's frames, as it does today. Whether to add one depends on the device's ACK deadline (overview, question P1); V1b measures it.

## Review Focus

1. A frame is acknowledged although nothing was stored (the anti-goal of the spec): every path of `_process_frame` that returns a confirm is behind `should_ack(outcome)`; the only acknowledged outcomes without a stored row are `DUPLICATE` and the two named exceptions `NO_ANCHOR` and `REJECTED`, each logged (T610 test `only the named outcomes are acknowledged without a row`).
2. One bad frame stops every device (a reconnect loop): no exception of the parser or of a handler leaves `_process_frame` unless the connection is closed; a CRC-valid frame whose latitude makes the parser raise is dropped with a WARNING and no ACK, and a frame the schema can never store is `REJECTED`, logged at ERROR and not retried for ever (T611).
3. An SOS is lost because the frame has no fix and no earlier fix: the alert is opened without a position (`ALERT_ONLY`, T613).
4. A frame that was stored is stored again: the retransmission inside the window is a `DUPLICATE` also when the store was slow, because the window starts when the store ends (T611, `a store slower than the window still catches the retransmission`).
5. A store that fails between the position and the SOS leaves a position with `sos_active` and no alert, and the retransmission then sees no rising edge: one transaction, rolled back as a whole (T613).

---

## 1. Design

### 1.1 Outcomes and the policy table (T610)

| Outcome | When | ACK | Marks the event as seen | Today |
|---------|------|-----|-------------------------|-------|
| `STORED` | the position or heartbeat is committed | yes | yes | ACK, seen **before** the store |
| `STORED_NOT_BROADCAST` | stored; the person is inactive, so no live message | yes | yes | the same |
| `ALERT_ONLY` | a no-fix frame with SOS and no earlier fix: the alert is committed, no position (T613) | yes | yes | dropped and acknowledged: **the SOS is lost** |
| `DUPLICATE` | same `EventID` for the device inside `EVENT_TIMEOUT` | yes | **no**: the window is never refreshed by a copy (today's `# update only if not repeated`; the unedited `test_same_event_after_timeout_is_handled_again` depends on it) | the same |
| `NO_ANCHOR` | a no-fix frame without SOS from a known device with no earlier fix; dropped by design (PROTOCOL.md) | yes | yes | the same |
| `REJECTED` | the store failed because of the frame's own content (a value the database refuses: SQLSTATE class 22, which includes a notification payload above the 8000 byte limit (22023) and the client-side encoding error for a value out of range), which a retransmission cannot cure | yes | yes | the error tears the reader down once; the retransmission is dropped and acknowledged |
| `UNKNOWN_DEVICE` | no active device row for the serial number and type | **no** | **no** | ACK, seen |
| `STORE_FAILED` | any other store failure: the connection, I/O, a serialization failure, a database in recovery, a missing table or column, a privilege error, a bug in the handler. The default, because a systematic fault must never acknowledge and drop frames | **no** | **no** | the error tears the reader down; the event stays seen, so the retransmission is dropped **and acknowledged** (R-06) |
| `UNPARSEABLE` | `parse_frame` returned nothing **or raised** (the parser's MGRS conversion raises `MGRSError`, which the parser does not catch, for a CRC-valid frame with a latitude outside the range or `nan`) | no | no | a raise ends the reader once; the retransmission raises again (a reconnect loop for every device) |

Three lines are defaults that the owner and the device maker are asked to confirm (overview, O2): `NO_ANCHOR` is acknowledged because the device is known and a retransmission cannot change the result; `REJECTED` is acknowledged (and logged at ERROR with the frame's `dev_sn`, `event_id` and the redacted reason) because a frame that can never be stored would otherwise be retransmitted for ever; `UNKNOWN_DEVICE` is not acknowledged, so the frame arrives again once an admin has registered the device (spec, section 5). A different answer is a one-line change of the table and of its test.

A handler result that is not an `Outcome` (a mock in an existing test) counts as `STORED`, so the unedited characterisation tests of `test_hid_process_frame.py`, which patch the handlers with mocks, keep their meaning.

### 1.2 The new shape of `_process_frame` (T611, T612)

```
try:    frame = parse_frame(raw)
except asyncio.CancelledError: raise
except Exception as exc:                      # the parser's MGRS conversion can raise
        log WARNING 'HID unparseable frame: %r (%s)' (reason through core.database.redact); return None   # no ACK: the MsgId is unknown
if frame is None                              -> return None (UNPARSEABLE)
if (dev_sn, event_id) seen inside the window  -> outcome = DUPLICATE
else:
    try:    outcome = await handler(frame, conn)
    except asyncio.CancelledError: raise
    except Exception as exc:
            outcome = classify_store_error(exc)          # STORE_FAILED or REJECTED
            log WARNING (STORE_FAILED) or ERROR (REJECTED):
                'Frame not stored (%s): dev_sn=%s event_id=%s reason=%s'   (reason through core.database.redact)
            if conn.is_closed(): raise                   (run() reconnects, as today)
    if marks_seen(outcome): remember (event_id, time.monotonic())   # read AFTER the handler returned
return make_confirm(frame.msg_id) if should_ack(outcome) else None
```

The window is refreshed only in the `else` branch: a `DUPLICATE` never refreshes it (that would turn the window into a sliding one), so `SEEN_POLICY[DUPLICATE]` is `False`. The parser is **not** changed (T601 pins it): the guard around `parse_frame` is the whole fix.

`classify_store_error(exc) -> Outcome` lives in `infrastructure/store_errors.py` (it imports asyncpg, so it is not domain code). **The safe default is `STORE_FAILED`**: a frame is dropped and acknowledged only for a reason that lies in the frame itself. `REJECTED` is `asyncpg.DataError` (SQLSTATE class 22: a value out of range for its column, an invalid parameter such as a notification payload that is too long, 22023) **when the server raised it** (`exc.severity is not None`: asyncpg fills `severity` only from a server message), or when asyncpg raised it on the client while encoding an argument **and its `__cause__` is an `OverflowError`** (a number outside the column's integer range: `prepared_stmt.pyx` raises `DataError(...) from e`). A client-side `DataError` with any other cause (a `TypeError` for `expected str, got int`, a naive datetime for an aware column) is a bug of the handler or the payload, recurs on every frame and is `STORE_FAILED`, for the same reason a bare `TypeError` is. Also `REJECTED`: `asyncpg.exceptions._base.DataError` (defined by asyncpg as an `InterfaceError` and a `ValueError`, not raised by the installed version as far as is known; kept as insurance and tested **before** the `InterfaceError` branch). Nothing else: a bare `ValueError`, `OverflowError` or `TypeError` is a bug of the handler or the payload (or a validation error of the typed payload model that wave 2's T547 adds), it recurs on every frame, and so it is `STORE_FAILED`. Everything else is `STORE_FAILED`, among them `asyncpg.ProgramLimitExceededError` (SQLSTATE 54000, which PostgreSQL also raises when the notification queue is full because a listener is stuck: a systemic, passing fault), `ValueError`, `OverflowError`, `TypeError`, `OSError`, `asyncpg.InterfaceError`, `asyncpg.PostgresConnectionError`, `asyncpg.TransactionRollbackError`, `asyncpg.InsufficientResourcesError`, `asyncpg.OperatorInterventionError`, and also a database in recovery (`ReadOnlySQLTransactionError`), a missing table or column (`UndefinedTableError`, `UndefinedColumnError`: a migration not applied), `InsufficientPrivilegeError`, a lock or session timeout, and any `KeyError` or `AttributeError` of the handler. The cost of that default is device air time for a systematic fault, never a lost frame. V1 shows which class a stopped database raises.

Bees and repeaters keep their two dictionaries and the 15 second window. An outcome that is not acknowledged is logged once at INFO: `'No ACK for dev_sn=%s event_id=%s: %s'`. Every log call passes `outcome.value` (`store_failed`), not the member: `'%s' % Outcome.STORE_FAILED` prints the member name on the Python versions in use, and the bench reads the lower-case text. The existing lines `HID frame extracted:`, `HID confirm to send:` and both `Repeated ... ignored` lines stay; the INFO line `No ACK` is written for an outcome that `_process_frame` returns without a confirm and not again for `STORE_FAILED`, which already has its WARNING; together they let the validation read every ACK decision from the backend log.

### 1.3 One transaction, and the SOS without a position (T613)

`_handle_bee` keeps its order of work. The device check stays outside (it stores nothing). The no-anchor check changes in one way: a no-fix frame without an earlier fix **and with `sos_active`** no longer returns; it opens the alert. Everything that writes runs inside one `async with conn.transaction():`:

- normal frame: `previous_sos_flag`, `insert_position`, `raise_sos` on a rising edge, `has_open_alert`, the person and team reads, `publish_position`: outcome `STORED` or `STORED_NOT_BROADCAST`;
- no anchor, SOS asserted: `sos_api.raise_sos` only (it checks for an open alert itself, so a device that keeps asserting SOS opens one alert, and sends the `sos_alert` message): outcome `ALERT_ONLY`. There is no position row to carry the previous flag, so after an operator resolved the alert the next such frame opens a new one; that is accepted (an alarm too many, never one too few) and stated in the PR: while a bee keeps asserting SOS without a fix, **Resolve cannot silence it**; every frame opens a new alert and a new `sos_alert` message until the SOS is cleared on the device (a cooldown after a resolve is a later change, not in this plan);
- no anchor, no SOS: no transaction, outcome `NO_ANCHOR`, as today.

`_handle_repeater` wraps its single `INSERT` the same way. Both `pg_notify` calls are inside the transaction and are delivered after the commit (ADR 7). The ACK is built by `_process_frame` after the handler returned, that is after the commit. The simulation gets the same transaction through `gateway.api.store_frame`.

## 2. Validation on a real gateway (run by Kiril Penev; the result table goes into each PR body)

**Bench.** A machine with the USB gateway, the database container of `docker/docker-compose.yaml` running (`podman ps` or `docker ps` shows its name), the backend started from the stacked branch `feature/vs-3-t613` (it contains T611 and T612) with `start.ps1` or `start.sh`, `ENABLE_TEST_ENDPOINTS` not set. One bee registered in the Devices page with its real `DevSN` (device A), one bee that is **not** registered (device B). The backend log is kept for the whole run. Rows are counted with `podman exec <db container> psql -U <user> -d <database> -c "SELECT count(*), max(received_at) FROM location_events WHERE device_id = '<id of A>'"` (Docker: the same with `docker exec`). Never run this on a machine that holds operation data.

| Check | For | Steps | Expected |
|-------|-----|-------|----------|
| V0 start | T602, T603, T604 (release gate), repeated before every other check | start the backend with the gateway plugged in; let A transmit twice | log: `HID device opened VID=... PID=...`; `GET /api/serial/status` shows `connected: true` and `frames_received` climbing; A is on the map; each frame has one `HID confirm to send:` line; the row count grows by one per frame |
| V2 unknown device (run early: it gives the retry numbers V3 needs) | T612 | let B transmit for five minutes; then register B in the Devices page | before: log `Unknown or inactive bee dev_sn=<B>`, a line `No ACK for dev_sn=<B>`, no `HID confirm to send:` for B's `MsgId`; write down **how many times and how often B retransmits one frame and when it gives up**. After registering: the next frame of B is stored, acknowledged and on the map |
| V1 failed store | T611 | while A transmits, stop the database container (`podman stop <db container>`), wait for at least two transmissions of A, start it again | during the outage: no `HID confirm to send:` line; lines `Frame not stored (store_failed)` and then the reader's reconnect lines (the first failed frame may be logged before the connection reports itself closed); A retransmits. After the start: the reader reconnects by itself, the retransmitted frame is stored **once** and acknowledged. Write down the exception class named in the `reason`. |
| V1b slow store | T611 (observe, no pass or fail) | `podman pause <db container>` for 20 seconds, then `podman unpause` (a rootless Podman machine needs cgroup v2 for `pause`) | write down: does A retransmit while the store hangs; are the copies that arrive after the unpause logged `Repeated BeeFrame ignored` and acknowledged without a second row; did any **other** device lose a frame during the 20 seconds. The answers decide whether a store timeout is needed |
| V3 lost ACK | T611; **only if** V2 showed a retry interval under 15 seconds | unplug the gateway's USB cable for less than the retry interval right after an ACK line appears in the log for A, so that the device does not get it (or any other way the device maker has to drop one ACK) | the retransmitted frame is logged `Repeated BeeFrame ignored`, is acknowledged, and the row count grew by one, not two. If the reader had to reconnect in between (5 seconds) and the retry came later than 15 seconds after the store, a second row is the known restart and window limit (section 4), not a FAIL: write down the timing |
| V4 SOS in one transaction | T613 | in a second terminal open an **interactive** session, `podman exec -it <db container> psql -U <user> -d <database>`, type `LISTEN sos_alert; LISTEN location_update;` and then `SELECT 1 \watch 1` (psql prints notifications only after a command returns); press SOS on A; resolve the alert in the banner; let A send two more frames with SOS still asserted | one `sos_alerts` row and one `location_events` row for the press; both notifications are printed in the same second and a `SELECT` at that moment already shows the rows; the banner shows once; the two later frames open no new alert; every frame has its ACK |
| V4b SOS without a fix | T613 | a bee that has never had a fix on this database (a fresh `DevSN` registered just now, indoors) presses SOS | one `sos_alerts` row, no `location_events` row; the banner shows with the person's name; the frame is acknowledged. If instead the log shows `HID unparseable frame` (a bee with no fix may send zero or invalid date fields, so the parser's `datetime(...)` fails and the frame never reaches the handler), the SOS is still lost: write down the raw frame; the fix (a fallback for `triggered_at`) is a parser change and is its own hardware-gated task. Also look at the banner of this alert: it has no position, so check that a "locate on the map" action does not break |
| V5 soak | T611 to T613 together, before the release | A, at least one more registered bee and one repeater transmit for 30 minutes | every `HID frame extracted:` line is followed by exactly one decision line, so the count of `HID frame extracted:` equals the sum of four counts: `HID confirm to send:`, `No ACK for`, `Frame not stored (store_failed)` and `HID unparseable frame` (the last two are expected to be zero; a `Frame not stored (rejected)` line is an ERROR next to a confirm and is counted with the confirms, also expected zero); the row counts of `location_events` and `repeater_events` equal the acknowledged frames that were neither duplicates nor `NO_ANCHOR` or `ALERT_ONLY` (those have no position row; none is expected on a bench with fixes); no `Frame not stored` line |

**Result table for the PR body** (one line per check): check, date, firmware version of the devices, PASS or FAIL, the numbers written down (V1, V1b, V2, V3), who ran it. A FAIL stops the merge and becomes a `B<n>` entry.

## 3. Task order, PRs, reviewers

| PR | Task | Content | Needs | Owner | Reviewers | Hardware |
|----|------|---------|-------|-------|-----------|----------|
| 1 | T610 | outcomes and the ACK policy table (pure) | gateway plan T602 | implementer | breaker | **no hardware gate**; follows T602, so it is held with it under O4 (T604 of the gateway plan needs it) |
| 2 | T611 | seen after the store; store errors are classified; a passing failure is not acknowledged | T610, T604 | implementer | breaker + security-reviewer (`hardware_reader/**`) | **waits**: V0, V1, V1b, V3 |
| 3 | T612 | no ACK for an unknown or inactive device | T611; the answer to O2 | implementer | breaker + security-reviewer | **waits**: V0, V2 |
| 4 | T613 | one transaction; SOS without a position | T612 | implementer | breaker + security-reviewer | **waits**: V0, V4, V4b, then V5 on the sum |

The three waiting tasks are a strict chain, stacked (`feature/vs-3-t612` off `feature/vs-3-t611`, `feature/vs-3-t613` off `feature/vs-3-t612`). They are **implemented and reviewed** as soon as T604 is merged; only the merge waits. One bench session on the top branch runs V0, V2, V1, V1b, V3, V4, V4b, V5; the three PRs are then merged in order on the same day.

**PR gate:** the gate of the gateway plan, plus the result table of section 2, plus the hardware note: "This PR changes the duplicate filter, the ACK or the store of a frame. Validated on a real gateway by Kiril Penev on <date>, checks <list>: results below. Not run against hardware by the agent."

## 4. Risks, rollback, not verified

| Risk | Mitigation |
|------|------------|
| T611 alone: the position is committed, `raise_sos` fails, the frame is not acknowledged; on the retransmission the previous flag is already true, so no alert is ever opened, and a second position row is stored | T613 makes it one transaction; the three merge together and no release is tagged between them (Global Constraints) |
| A device that is never acknowledged retransmits without limit; every copy costs a `devices` read and a WARNING line | measured in V2 before T612 is merged; the policy is one line of the table; a rate limit for the log line is a follow-up if V2 shows a flood |
| A frame the schema can never store (`MsgId` or `Course` outside SMALLINT: the parser checks no ranges) | `REJECTED` (a `DataError`): logged at ERROR, acknowledged, not retried; test in T611 |
| A CRC-valid frame with a latitude outside the range or `nan`: the parser's MGRS conversion raises `MGRSError` (not a `ValueError`) before any store | the guard around `parse_frame` (section 1.2): WARNING, no ACK, the reader stays up; the retransmission is dropped the same way, so the device retries on its own schedule (P1) |
| A frame that is `REJECTED` and carries SOS: the position insert comes before the alert, so a `DataError` on the position drops the SOS (as today, now with an ERROR line); an oversized `location_update` rolls back the alert opened in the same transaction | accepted in this plan and written in the PR; a fallback `ALERT_ONLY` attempt for a `REJECTED` frame with `sos_active` is the follow-up if V4 or the log shows one |
| A `nan` or infinite coordinate in a CRC-valid frame faults inside the native MGRS library: `OSError` on Windows (measured: `.venv\Scripts\python -c "import mgrs; mgrs.MGRS().toMGRS(42.0, float('nan'))"`), not measured on Linux, where it may end the backend process | T611 keeps such a frame away from the parser (a field check in `_process_frame`); the maintainer is asked to run the same command on Linux (overview, M9) and the device maker whether a device can send it (P6) |
| The parser raising on a CRC-valid frame is not acknowledged (the `MsgId` is unknown) while a `REJECTED` store is: the same kind of frame is retried for ever in one case and dropped in the other | waits for P1 and P6; `nan` as longitude makes the native MGRS library raise `OSError` (an access violation), not `MGRSError`: the guard catches `Exception`, and the device maker is told |
| A systematic store fault (a migration not applied, a read-only standby, a privilege error) | `STORE_FAILED`: no ACK, nothing dropped; the device retransmits until the fault is fixed |
| The commit makes the ACK later than the device's deadline, so stored frames are retransmitted | the copies are `DUPLICATE` because the window starts when the store ends (V1b, V3); the deadline is asked from the device maker |
| The window holds one `EventID` per device, so a late copy of an older event (after a newer one was stored) is stored twice | exists today; more likely when ACKs are later; stated, not fixed (a fix needs `EventID` in `location_events`, a migration, step 4 or later) |
| The first frame after a restart is a retransmission of a frame stored before the restart | the same limit: the dictionary is in memory |
| A `location_update` payload above the 8000 byte limit of `pg_notify` now rolls back the position too (today the row is already committed) and is `REJECTED` (it is SQLSTATE 22023, a `DataError`) | only possible while names and teams are in the payload (a person in very many teams with long Cyrillic names); gone when `LIVE_PERSONAL_FIELDS` is off; T613 adds the test `an oversized notification is rejected and logged, not retried`; recommended to T547: drop `groups` from a payload that would exceed the limit |
| `stop_module_tasks` awaits the reader's `conn.close()`; with a frozen database the shutdown can hang | exists since T603; stated in the overview |
| The simulation's SOS behaves differently inside the transaction | `store_frame` runs the same handler; smoke steps e and l cover it without hardware |

**Rollback.** No schema or data change. Revert newest first and all three together: T613, T612, T611; each revert restores the matching `FROZEN` literal because it is in the same commit. T610 stays (T604 uses it).

**Not verified while planning:** the device's retry count, retry interval and ACK deadline (unknown, asked); which exception class `asyncpg` raises when the container stops mid-statement and whether `is_closed()` is already true at that moment (V1 writes it down; the design is right either way: the next statement raises on the closed connection and `run` reconnects); nothing was run on hardware.

## 5. Existing tests

| File | Edit | Kind | Task |
|------|------|------|------|
| `backend/tests/modules/gateway/test_hid_process_frame.py` | the `xfail` marker of `test_failed_store_does_not_mark_the_event_seen` is removed | deliberate: the debt it names is paid | T611 |
| the same file | the `xfail` marker of `test_unknown_device_frame_is_not_acked` is removed | deliberate | T612 |
| the same file | the `xfail` marker of `test_bee_frame_is_stored_in_one_transaction` is removed | deliberate | T613 |
| `backend/tests/modules/gateway/test_gateway_api.py` (written in T604) | `test_process_frame_does_not_read_the_outcome_yet` is deleted: from T611 on the outcome decides | deliberate | T611 |
| `backend/tests/modules/gateway/test_gateway_api.py`, `backend/tests/test_simulation*.py`, `test_api_simulate.py` (T604, T621) | any test that runs a real handler on a bare `AsyncMock()` connection gets the transaction mock of `delegates_helper` (found with `git grep -n "AsyncMock()" backend/tests/modules/gateway backend/tests/test_api_simulate.py`); none is expected, T604 forbids it | only if such a test exists | T613 |
| `backend/tests/modules/gateway/frozen_hashes.py` | the literal of `hid_reader._process_frame` | deliberate, regenerated | T611, T612 |
| `backend/tests/modules/gateway/gateway_fakes.py` | `GatewaySql` gets `fail_on(fragment: str, exc: Exception)` (the next statement whose text contains `fragment` raises `exc`) and a record of the inserts of committed transactions | new helper | T613 |
| `backend/tests/modules/gateway/delegates_helper.py` | `run_case` builds its connection with `conn.transaction` set to a `MagicMock` that returns an async context manager (an `AsyncMock().transaction()` is a coroutine and `async with` on it raises `TypeError`, which would fail all six cases of `test_reader_delegates.py`, T604's `test_store_frame_runs_the_same_statements_as_the_handler` and T613's own statement-order test). The expected statement lists stay identical: a transaction adds no statement to the recorded `(method, sql, args)` lists | deliberate: the code under test now opens a transaction | T613 |
| `backend/tests/modules/gateway/test_reader_handlers.py`, `test_reader_delegates.py` | the case of a no-fix frame without an earlier fix stays as it is (no SOS: nothing stored); nothing to edit unless a case uses a no-anchor frame **with** SOS, which then expects the alert | deliberate, only if such a case exists | T613 |

The bodies of the three former `xfail` tests are not edited: they were written against the intended behaviour. `mock_conn` is an `AsyncMock`, so `conn.is_closed()` on it returns a truthy coroutine; the old failed-store test accepts both the swallowed and the raised shape and passes either way. Every **new** test of T611 to T613 therefore sets `mock_conn.is_closed = MagicMock(return_value=False)` in a fixture, and the closed-connection test sets it to `True`. A characterisation test that fails is a finding, not something to adapt.

## 6. Open questions (details in the overview, section 7)

1. **To the device maker:** retry count, retry interval and ACK deadline of a bee and a repeater; is there a negative acknowledgement; does `EventID` restart after a device reboot; does an unacknowledged frame block the device's later frames.
2. **To the owner and the device maker:** the policy lines `NO_ANCHOR` (ACK), `REJECTED` (ACK, ERROR log), `UNKNOWN_DEVICE` (no ACK), and the new behaviour `ALERT_ONLY` (an SOS without any fix opens an alert without a position).
3. **To the owner:** who runs section 2, on which gateway, in which window (spec section 9, question 2).

---

### Task 610: outcomes and the ACK policy table

**risk:** normal
**owner:** implementer
**hardware:** safe (pure; no reader imports it in this task); it needs the package of T602, so it is held with T602 under O4
**Files:**
- Create: `backend/modules/gateway/domain/outcome.py`, `backend/tests/modules/gateway/test_outcome.py`

**Interfaces:**
- Produces: `class Outcome(str, enum.Enum)` with the members `STORED = 'stored'`, `STORED_NOT_BROADCAST = 'stored_not_broadcast'`, `ALERT_ONLY = 'alert_only'`, `DUPLICATE = 'duplicate'`, `NO_ANCHOR = 'no_anchor'`, `REJECTED = 'rejected'`, `UNKNOWN_DEVICE = 'unknown_device'`, `STORE_FAILED = 'store_failed'`, `UNPARSEABLE = 'unparseable'`; `ACK_POLICY: dict[Outcome, bool]` and `SEEN_POLICY: dict[Outcome, bool]` with the values of section 1.1 (`DUPLICATE` is `False` in `SEEN_POLICY`: a copy never refreshes the window); `should_ack(outcome: object) -> bool` and `marks_seen(outcome: object) -> bool`, both returning `True` for a value that is not an `Outcome`.

- [ ] **Step 1: Write the failing tests**, tagged `T610`: `test_the_policy_is_the_table_of_the_plan` (two literal dictionaries equal `ACK_POLICY` and `SEEN_POLICY`); `test_every_outcome_has_both_policies`; `test_only_the_named_outcomes_are_acknowledged_without_a_row` (the acknowledged outcomes are exactly `STORED`, `STORED_NOT_BROADCAST`, `ALERT_ONLY`, `DUPLICATE`, `NO_ANCHOR`, `REJECTED`); `test_an_unacknowledged_outcome_never_marks_the_event_seen`; `test_a_handler_result_that_is_no_outcome_counts_as_stored` (`None`, `object()` and a `MagicMock`); `test_the_module_is_pure` (its source imports only `enum` and `__future__`).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\gateway\test_outcome.py -q`. Expected: FAIL with `ModuleNotFoundError: No module named 'backend.modules.gateway.domain.outcome'`.
- [ ] **Step 3: Implement** the file.
- [ ] **Step 4: Run.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\gateway backend\tests\architecture -q`. Expected: PASS (`domain is pure` included; T601 hashes untouched).
- [ ] **Step 5: Commit** `feat(gateway): T610 frame outcomes and the ACK policy table`. PR body: the table of section 1.1, addressed to the owner and the device maker for a yes or a correction.

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\gateway backend\tests\architecture -q`

### Task 611: a frame is marked as seen after the store, and store errors are classified

**risk:** security
**owner:** implementer
**hardware:** **waits for hardware.** Merged only after Kiril Penev ran V0, V1, V1b and V3 of section 2 (on the stacked branch that also holds T612 and T613); the result table is in the PR body. Merged on the same day as T612 and T613.
**Files:**
- Create: `backend/modules/gateway/infrastructure/store_errors.py`, `backend/tests/modules/gateway/test_ack_after_store.py`, `backend/tests/modules/gateway/test_store_errors.py`
- Modify: `backend/modules/gateway/infrastructure/hid_reader.py` (`_process_frame` and the imports it needs: `Outcome`, `classify_store_error`, `redact`; no other function; in `backend/tests/modules/gateway/test_gateway_api.py` the test `test_process_frame_does_not_read_the_outcome_yet` of T604 is deleted; `should_ack` and `marks_seen` are imported in T612, not here)
- Modify: `backend/tests/modules/gateway/test_hid_process_frame.py` (one marker), `frozen_hashes.py` (one literal), `backend/tests/architecture/importlinter.toml` only if `check_boundary_contracts` asks for the new file (it lists private children by folder, and `infrastructure` is already there)

**Interfaces:**
- Consumes: T610 (`Outcome` only; the ACK and window rule of this task is the inline `outcome is not Outcome.STORE_FAILED`, see below); the handlers' outcomes (T604 of the gateway plan).
- Produces `store_errors.py`: `classify_store_error(exc: BaseException) -> Outcome` as section 1.2 says.
- Produces in `hid_reader.py`, before the call of `parse_frame`: a frame whose latitude or longitude field, stripped and lower-cased with an optional sign removed, is `nan`, `inf` or `infinity` is `UNPARSEABLE` (the same WARNING, no ACK, not seen) and never reaches the parser. The fields are split the way the parser splits them; the parser itself is pinned and not edited. Reason: on such a value the native MGRS library faults, and outside Windows a fault is a signal that no `except` catches.
- Produces in `hid_reader.py`: `_process_frame` has the shape of section 1.2 with one difference kept for T612: T611 uses a temporary rule, `outcome is not Outcome.STORE_FAILED`, for both the ACK and the window (so `UNKNOWN_DEVICE` is acknowledged and seen as today); it does **not** call `should_ack` and `marks_seen` yet, because with the T610 table an unknown device would stop being acknowledged one task early. T612 replaces the temporary rule by the two functions. The window time is read after the handler returned.

- [ ] **Step 1: Write the failing tests**, tagged `T611`. A fixture sets `mock_conn.is_closed = MagicMock(return_value=False)`. Every hand-built class 22 error that stands for a server error gets `severity = 'ERROR'` on the instance (a helper `server_error(cls, message)` in the test file), in `test_classification` too. `test_store_errors.py`: `test_a_client_side_type_mismatch_is_not_rejected` (a hand-built `asyncpg.DataError('invalid input for query argument $1: 5 (expected str, got int)')` with `__cause__` set to a `TypeError`, and one with no cause: both `STORE_FAILED`); `test_a_server_side_data_error_is_rejected` (`asyncpg.NumericValueOutOfRangeError` with `severity = 'ERROR'` set on the instance: `REJECTED`; the same class with `severity` `None` and no cause: `STORE_FAILED`); the hand-built error of the next test has `__cause__` set to an `OverflowError`; `test_a_client_side_encoding_overflow_is_rejected` (`asyncpg.DataError('invalid input for query argument $1: 70000 (value out of int16 range)')`, built by hand because asyncpg has no public database-free encoder entry point, gives `REJECTED`; the first bench run of V1 or V5 shows the real class and the PR body writes it down); `test_classification` (parametrised: `asyncpg.exceptions._base.DataError`, `asyncpg.DataError`, `asyncpg.NumericValueOutOfRangeError`, `asyncpg.InvalidParameterValueError` give `REJECTED`; `OSError`, `ConnectionResetError`, `asyncpg.InterfaceError`, `asyncpg.ConnectionDoesNotExistError`, `asyncpg.SerializationError`, `asyncpg.DeadlockDetectedError`, `asyncpg.AdminShutdownError`, `asyncpg.QueryCanceledError`, `asyncpg.TooManyConnectionsError`, `asyncpg.ReadOnlySQLTransactionError`, `asyncpg.UndefinedTableError`, `asyncpg.UndefinedColumnError`, `asyncpg.InsufficientPrivilegeError`, `asyncpg.UniqueViolationError`, `KeyError`, `AttributeError`, `RuntimeError`, `ValueError('x')`, `OverflowError`, `TypeError`, `asyncpg.ProgramLimitExceededError` give `STORE_FAILED`). `test_ack_after_store.py` (handlers patched as in `test_hid_process_frame.py`, with its controlled clock): `test_a_failed_store_sends_no_ack_and_the_retransmission_is_stored`; `test_a_retransmission_of_a_stored_frame_is_acked_and_not_stored_twice`; `test_a_duplicate_does_not_refresh_the_window` (frame at t, the same frame at t+14.5 s is a duplicate, the same frame at t+15.5 s is handled again: the existing `test_same_event_after_timeout_is_handled_again` must stay green); `test_a_store_slower_than_the_window_still_catches_the_retransmission` (the handler advances the clock by 20 seconds before it returns; the same frame one second later is a duplicate); `test_a_frame_that_can_never_be_stored_is_rejected_acked_and_logged_at_error` (the handler raises `asyncpg.NumericValueOutOfRangeError` every time: the first call returns the confirm and logs at ERROR; the second call inside the window does not call the handler); `test_an_unexpected_exception_does_not_leave_process_frame` (`RuntimeError`: no ACK, not seen, WARNING); `test_a_crc_valid_frame_with_latitude_95_does_not_leave_process_frame` (a frame built with `make_frame` from `BEE_BODY` with field 12 set to `95.0` and field 11 `A`: the parser raises `MGRSError`; the result is `None`, a WARNING `HID unparseable frame` is logged, the handler is not awaited); the same for latitude `nan` and longitude `inf`; `test_an_oserror_of_the_parser_is_caught` (`parse_frame` patched to raise `OSError`: same result; the real library is **not** fed a `nan` longitude in any test, because the fault is an access violation that ctypes turns into `OSError` on Windows and that may kill the process on Linux, where CI runs); `test_a_nan_or_inf_coordinate_never_reaches_the_parser` (frames whose latitude or longitude field is `nan`, `NaN`, `inf`, `-inf` or `Infinity`: `parse_frame`, patched by a recorder, is not called; WARNING `HID unparseable frame`; no confirm; the event is not seen); `test_cancellation_is_not_swallowed`; `test_a_failed_repeater_store_sends_no_ack`; `test_the_reason_is_logged_without_the_password`; `test_a_closed_connection_is_not_swallowed` (`is_closed` true: the error propagates and the event is not seen). Remove the `xfail` marker of `test_failed_store_does_not_mark_the_event_seen`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\gateway\test_ack_after_store.py backend\tests\modules\gateway\test_store_errors.py backend\tests\modules\gateway\test_hid_process_frame.py -q`. Expected: FAIL (`No module named '...store_errors'`; `1235` is in `bee_last_events` after the failed store).
- [ ] **Step 3: Implement**, then regenerate the literal of `hid_reader._process_frame`.
- [ ] **Step 4: Run.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_parser.py -q`. Expected: PASS; two `xfail` tests are left; `git diff upstream/develop -- backend/tests/modules/gateway/frozen_hashes.py` shows one changed literal.
- [ ] **Step 5: Commit** `fix(gateway): T611 a frame is marked seen after the store and store errors are classified`.
- [ ] **Step 6: Hand over for validation.** Push the branch and write the PR body with the empty result table of section 2 (V0, V1, V1b, V3) and stop: the PR is opened by the human and merged only with the table filled, together with T612 and T613.

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_parser.py -q`

### Task 612: no ACK for an unknown or inactive device

**risk:** security
**owner:** implementer
**hardware:** **waits for hardware.** Merged only after Kiril Penev ran V0 and V2 of section 2, and after the owner and the device maker have confirmed the policy table of T610 (the retransmission numbers of V2 are part of that answer). Merged on the same day as T611 and T613.
**Files:**
- Modify: `backend/modules/gateway/infrastructure/hid_reader.py` (`_process_frame` only)
- Modify: `backend/tests/modules/gateway/test_hid_process_frame.py` (one marker), `frozen_hashes.py` (one literal)
- Create: `backend/tests/modules/gateway/test_ack_policy_wired.py`

**Interfaces:**
- Consumes: T610 (`should_ack`, `marks_seen`), T611.
- Produces in `hid_reader.py`: `_process_frame` returns the confirm only when `should_ack(outcome)` and remembers the event only when `marks_seen(outcome)`; an outcome that is not acknowledged is logged at INFO as `'No ACK for dev_sn=%s event_id=%s: %s'` with `outcome.value`, except `STORE_FAILED` set in the `except` block (it already has its WARNING) and `UNPARSEABLE` (its own WARNING).

- [ ] **Step 1: Write the failing tests**, tagged `T612` (the `is_closed` fixture of T611): `test_every_outcome_is_acked_exactly_as_the_table_says` (parametrised over `Outcome` without `DUPLICATE` and `UNPARSEABLE`: the handler returns the outcome; no real handler returns `STORE_FAILED`, that parameter only proves the table is obeyed; the result is a confirm or `None` as `ACK_POLICY` says, and the device is in the window dictionary as `SEEN_POLICY` says); `test_an_unknown_device_is_stored_and_acked_after_it_is_registered` (first frame `UNKNOWN_DEVICE`, no ACK; the same frame again inside the window with the handler now returning `STORED`: handled and acknowledged); `test_a_no_anchor_frame_is_acked_and_not_handled_twice`; `test_the_refusal_is_logged_once_per_frame` (an unknown device: one INFO `No ACK` line and no `Frame not stored` line; a raised connection error: one WARNING `Frame not stored (store_failed)` line and no `No ACK` line); `test_a_mocked_handler_without_an_outcome_is_acked`. Remove the `xfail` marker of `test_unknown_device_frame_is_not_acked`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\gateway\test_ack_policy_wired.py backend\tests\modules\gateway\test_hid_process_frame.py -q`. Expected: FAIL (an unknown device is acknowledged).
- [ ] **Step 3: Implement**, then regenerate the literal.
- [ ] **Step 4: Run.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_parser.py -q`. Expected: PASS; one `xfail` test is left.
- [ ] **Step 5: Commit** `fix(gateway): T612 an unknown or inactive device gets no ACK`.
- [ ] **Step 6: Hand over for validation** (V0, V2; the PR body has the numbers "retransmissions per frame", "interval", "gives up after").

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_parser.py -q`

### Task 613: position, SOS and notifications in one transaction; an SOS without a position opens the alert

**risk:** security
**owner:** implementer
**hardware:** **waits for hardware.** Merged only after Kiril Penev ran V0, V4 and V4b of section 2, and V5 on the sum of T611 to T613. Merged on the same day as T611 and T612.
**Files:**
- Modify: `backend/modules/gateway/infrastructure/reader.py` (`_handle_bee`, `_handle_repeater`)
- Modify: `backend/tests/modules/gateway/test_hid_process_frame.py` (one marker), `gateway_fakes.py` (`fail_on`, and a record of the inserts that were made), `delegates_helper.py` (`run_case`: `conn.transaction` is set to a `MagicMock` returning an async context manager, as `backend/tests/conftest.py::mock_conn` does)
- Create: `backend/tests/modules/gateway/test_one_transaction.py`

**Interfaces:**
- Consumes: T612; `gateway_fakes.GatewaySql.record_transactions` (it already logs `begin`, `commit` and `rollback`); `fail_on('commit', exc)` makes the commit of the fake transaction raise.
- Produces in `reader.py`: the transaction and the `ALERT_ONLY` rule of section 1.3. `_handle_bee` opens no transaction for `UNKNOWN_DEVICE` and `NO_ANCHOR`. An exception inside the block leaves it (rollback) and reaches `_process_frame`, which classifies it. The statements of the normal path, their texts and their order are unchanged; `hid_reader.py` is not edited, so no frozen literal changes.

- [ ] **Step 1: Write the failing tests**, tagged `T613` (the `is_closed` fixture of T611), in `test_one_transaction.py`: `test_a_failure_after_the_position_insert_leaves_no_row_and_no_notification` (`sql.fail_on('INSERT INTO sos_alerts', asyncpg.ConnectionDoesNotExistError('boom'))`: the log has `('tx', 'begin')`, then `('tx', 'rollback')`, no `('tx', 'commit')`, and `_process_frame` returns `None`); `test_the_retransmission_after_that_failure_opens_the_alert` (the fake records the inserts of committed transactions and derives the previous flag from them: after the rolled-back first call the record is empty and the previous flag is false, so the second call stores the position and the alert in one committed transaction; with a handler that does not use a transaction the first call would have left a position row and this test fails); `test_a_plain_position_is_one_transaction_with_its_notification_inside`; `test_an_inactive_person_is_stored_in_a_transaction_without_a_notification`; `test_an_unknown_device_opens_no_transaction`; `test_a_no_anchor_frame_without_sos_opens_no_transaction`; `test_a_no_anchor_frame_with_sos_opens_the_alert_and_is_acked` (one transaction with `INSERT INTO sos_alerts` and the `sos_alert` notification, no `INSERT INTO location_events`; outcome `ALERT_ONLY`); `test_a_heartbeat_is_one_transaction`; `test_an_oversized_notification_is_rejected_and_logged_not_retried` (`fail_on('pg_notify', exc)` with `exc = asyncpg.InvalidParameterValueError('payload string too long')` and `exc.severity = 'ERROR'`, as the server sends it: rollback, ERROR line, confirm returned); `test_a_full_notification_queue_is_not_acknowledged` (`asyncpg.ProgramLimitExceededError('too many notifications in the NOTIFY queue')`: rollback, no confirm, WARNING); `test_a_failure_at_commit_is_not_acknowledged` (PostgreSQL raises the full-queue error at COMMIT, not at the `pg_notify` call: `fail_on('commit', ...)` makes the fake transaction's exit raise the same error; no confirm, WARNING, the event is not seen, nothing is in the record of committed inserts); `test_the_statements_and_their_order_are_unchanged` (the six literal lists of `test_reader_delegates.py` still match). Remove the `xfail` marker of `test_bee_frame_is_stored_in_one_transaction`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\gateway\test_one_transaction.py backend\tests\modules\gateway\test_hid_process_frame.py -q`. Expected: FAIL (`GatewaySql` has no `fail_on`; then no `('tx', 'begin')` in the log).
- [ ] **Step 3: Implement** the fake's helper, the `delegates_helper.py` edit, the transaction and the `ALERT_ONLY` branch. `test_reader_holds_no_sql_for_positions_or_alerts` (T542) forbids the words `INSERT INTO`, `location_events`, `sos_alerts`, `repeater_events` and `pg_notify` anywhere in `reader.py`, comments included: the new code and its comments must not use them.
- [ ] **Step 4: Run** the DoD and the smoke. Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_parser.py backend\tests\test_api_simulate.py backend\tests\test_simulation.py -q`. Expected: PASS; `git grep -n "pytest.mark.xfail" backend/tests/modules/gateway` prints nothing. Then `python tools/smoke.py`: steps e and l PASS (the simulated frame and the simulated SOS go through the same transaction).
- [ ] **Step 5: Commit** `fix(gateway): T613 a frame is stored and announced in one transaction, and an SOS without a fix opens its alert`.
- [ ] **Step 6: Hand over for validation** (V0, V4, V4b; then V5 on the stacked sum).

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_parser.py backend\tests\test_api_simulate.py backend\tests\test_simulation.py -q`
