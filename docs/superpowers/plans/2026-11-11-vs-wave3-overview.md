# Vertical slices, wave 3 (step 3: the gateway): overview of the four plans (merge order, chains, hardware gate, open questions)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Say in one place how the 15 tasks of wave 3 are ordered, which can start today without a gateway on the desk and which wait for one, which files are shared and in what order they are edited, what is asked from whom, and close the wave with one check on `develop`.

**Architecture:** Four plans. The gateway plan moves the hardware reader into a module without changing it and proves that with a hash pin. The hardware plan changes the duplicate filter, the ACK and the store and is merged only after a run on a real gateway. The tracking plan takes the clean-up out of `main.py` and sends the simulation through the gateway. The frontend plan gives the gateway status a module and finishes the tracking contributions. This document adds one task of its own: T690, the closing check.

**Tech Stack:** as in the four plans; no new dependency and no migration in the whole wave.

**Spec:** [`docs/superpowers/specs/2026-10-31-vertical-slices-programme-design.md`](../specs/2026-10-31-vertical-slices-programme-design.md) sections 2, 3, 5 ("Step 3"), 6, 9; `Architecture/application/modular-monolith.md` sections 3, 4, 5.1, 7, 9, 10; ADR 17, 18, 19, 20, 21; `Architecture/governance/risk-register.md` R-06, R-07, R-22; `docs/PROTOCOL.md`.

**Plans:**

1. [`2026-11-11-vs-step3-gateway-backend.md`](2026-11-11-vs-step3-gateway-backend.md): the allowlist tool, the hash pin, the `gateway` module, its task, `gateway.api` (T600 to T604, 5 tasks).
2. [`2026-11-11-vs-step3-hardware-path.md`](2026-11-11-vs-step3-hardware-path.md): outcomes and the ACK policy, ACK after store, no ACK for an unknown device, one transaction, the SOS without a fix, and the validation protocol for the real gateway (T610 to T613, 4 tasks).
3. [`2026-11-11-vs-step3-tracking-leftovers.md`](2026-11-11-vs-step3-tracking-leftovers.md): retention and the fire clean-up as module tasks, the simulation through the gateway (T620, T621, 2 tasks).
4. [`2026-11-11-vs-step3-frontend.md`](2026-11-11-vs-step3-frontend.md): the frontend `gateway` module, the tracker panel and the tracker layers as `tracking` contributions (T630 to T632, 3 tasks; T631 and T632 are wave 2's T548 and T549 with new numbers).

**Base:** `upstream/develop` at `d174ce3` (PR #150, T542 merged; `git fetch upstream; git log --oneline -1 upstream/develop` on 2026-11-11).

**Review:** four rounds so far (`f92c977`, `546fb5e`, `30881ab`, `cb7a653`), each by `task-reviewer` and `breaker`; every round's findings are applied in the next commit (section 10). Round 4: `task-reviewer` approved with no blocker; `breaker` failed it on two findings (a T604 test that T612 would break, and a platform-dependent `nan` test), both applied here. A plan review is not the PR gate: each task's PR still needs its own reviewers on its head.

## Global Constraints

- Decisions that are not reopened: those of wave 2's overview (base branch, kernel names, frozen files, aliases until step 5, auth by default, no WebSocket security work, `frontend-designer` for `.vue` and `.css`, the shell contract, `lib/groups.js`, `fire_alert*` payloads untouched).
- One task is one PR into `develop`. Every PR passes `python tools/smoke.py` before it is opened (a merge deploys to bee-dev), then `breaker` and, where section 5 says so, `security-reviewer` on the head commit; `gh pr create` is run by the human with `--body-file`. A conflict is solved by merging `upstream/develop` into the feature branch: no rebase, no force-push.
- **Hardware gate (merge).** T611, T612 and T613 edit the duplicate filter, the ACK and the store of a frame. They are merged only after Kiril Penev has run their stacked branches on a real gateway with the protocol of the hardware plan, section 2, and the result table is in each PR body; they are merged together, in order, on one day. The agent never runs anything against a gateway, a field machine or bee-dev.
- **Hardware gate for the move (T602, T603, T604).** These change no decode, duplicate-filter or ACK line (T601 proves it), but they change which code starts and runs the reader. The spec's section 3 asks for validation on a real gateway before merge and section 5 lets the owner split the step into "move only" and "fix". The wave proposes: check V0 as a **release gate** (field machines run tagged releases; `develop` reaches only bee-dev, which has no gateway). That needs the owner's yes (O4). Until then the three are implemented, reviewed and held as open PRs; with a no, V0 is run on each branch before its merge.
- Schema: no task has a migration. A schema change that a later decision adds is a new numbered file in `backend/db/migrations/`, additive, reviewed by `ef-migration-reviewer`; `0008` and `0009` are reserved by step 4. Never `compose down -v`, never delete `data/`.
- Task numbers: T600 to T604 plan 1, T610 to T613 plan 2, T620 and T621 plan 3, T630 to T632 plan 4, T690 this file. `git grep -nE "\bT6[0-9]{2}\b"` on `d174ce3` prints nothing.
- No plan of this wave points at a line number, and none states a count that was not read from `d174ce3`; where a count matters the plan names the command that prints it.

## Review Focus

1. A frame is acknowledged before it is stored, or lost between a failed store and its retransmission, at any point of the wave (the spec's first anti-goal): the move tasks cannot change it (T601 pins the functions), the fix tasks are validated on hardware before they merge, and they merge as one unit.
2. One bad frame, or one device that is never acknowledged, takes the reader away from every other device: store errors are classified, nothing but a closed connection leaves `_process_frame`, and V2 measures the retransmissions before the policy is fixed.
3. A branch that edited `reader.py` meets the move of T602 and the edit lands in the alias file or is lost: T547 merges before T602; every later branch merges `upstream/develop` and reruns its DoD.
4. The reader or the daily clean-up stops being started when its start moves from `main.py` to a manifest (T603, T620): each has a test through `start_module_tasks`, and V0 checks the reader on real hardware.
5. bee-dev's only data source is the simulation: T621 changes how it writes; smoke steps e and l, the CI run of the `db`-marked tests and a manual run of test mode (including Stop and Start without Reset) gate that PR.

---

## 1. Dependencies

```mermaid
flowchart LR
    T547[T547 wave 2] --> T602
    T600 --> T602
    T601 --> T602
    T602 --> T603
    T602 --> T610 --> T604
    T602 --> T604
    T604 --> T611 --> T612 --> T613
    T600 --> T620 --> T621
    T604 --> T621
    T547 --> T621
    T545[T545 wave 2] --> T630 --> T631 --> T632
    T590[T590 wave 2] --> T690
    T603 & T604 & T610 & T620 & T621 & T630 & T631 --> T690
```

Starting points with no dependency: T600, T601, and T545 followed by T630; T620 as soon as T600 is merged. Waiting for the owner's answer O4 or for V0: T602, T603, T604 and everything behind them; T610 is pure but needs the `gateway` package of T602, so with O4 = no it waits too. Waiting for the bench: T611, T612, T613. Optional end: T632. T690 does not wait for T611 to T613 or for T632; it reports their state.

## 2. Chains (one session at a time per chain)

| Chain | Hot file(s) | Order |
|-------|-------------|-------|
| reader | `backend/hardware_reader/reader.py`, after T602 `backend/modules/gateway/infrastructure/reader.py` | T547 (wave 2, in progress), T602 (move), T604 (return values, one keyword), T613 (transaction, SOS without a fix) |
| ACK | `hid_reader.py` (`_process_frame`), `backend/tests/modules/gateway/frozen_hashes.py` | T601 (creates the pin), T602 (move, literals untouched), T611, T612 |
| gateway tests | `backend/tests/modules/gateway/test_hid_process_frame.py`, `gateway_fakes.py`, `delegates_helper.py` | T604 (`delegates_helper`: the `call` parameter), T611, T612, T613 (one `xfail` marker each; `gateway_fakes` and `delegates_helper`, the transaction mock, in T613) |
| gateway module | `backend/modules/gateway/module.py`, `api.py`, `tests/modules/gateway/test_gateway_module.py` | T602 (creates), T603 (`module.py`, the manifest test), T604 (`api.py`) |
| backend assembly | `backend/main.py`, `backend/modules/registry.py`, `backend/tests/architecture/importlinter.toml`, `approved_additions.py`, `allowlist.json` | T602, T603 (TOML: `gateway.tasks`), T620 (TOML: `tracking.tasks`; another block of `lifespan`; one JSON row), T621 (JSON rows, approvals), T690 |
| tracking and sos API | `backend/modules/tracking/api.py`, `infrastructure/repository.py`, `backend/modules/sos/api.py`, `infrastructure/repository.py` | T547 (wave 2), T620 (adds one function), T621 (removes two), T613 (`publish_position` returns a flag) |
| simulation | `backend/routers/test.py`, `backend/simulation.py`, `test_api_simulate.py`, `test_simulation.py` | T547 (wave 2), T621 |
| smoke | `tools/smoke.py`, `backend/tests/test_smoke_script.py`, `docs/SMOKE.md` | T602 (step k), T621 (step l and one existing assertion): adjacent lines, keep both |
| tooling | `backend/tests/architecture/regen.py` | T600 only; T602, T620, T621 use it |
| map | `frontend/src/views/MapView.vue`, `frontend/src/composables/useMap.js` | T545 (wave 2), T630, T631, T632 |
| frontend assembly | `frontend/src/modules/index.js`, `frontend/src/i18n/en.js`, `bg.js`, `frontend/src/modules/tracking/index.js`, `frontend/src/architecture.allowlist.json` | T630, T631, T632 (the same session as the map chain); T590 then T690 for the allowlist file |

## 3. Merge order and parallel sessions

| Stage | Merged in this stage | Hardware | Why the stage is safe |
|-------|----------------------|----------|-----------------------|
| A (today) | T600, T601, T545 (wave 2) | none | a test tool, a new test file, the SOS toast: no shared file |
| B | T620, T630, and T547 (wave 2) when it is ready | none | `main.py`'s clean-up block and two task files; the map chain; the reader and simulation chains |
| C | T602, T631 | T602: O4 or V0 | backend assembly; map chain |
| D | T603, T610, T632 | T603: O4 or V0 | `lifespan`; a new pure file; map chain |
| E | T604 | O4 or V0 | reader chain |
| F | T621 | none of its own | simulation chain; smoke step l |
| G | T590 (wave 2), then T690 | none | closing checks on `develop` |
| H (when the bench is available) | T611, T612, T613, together | **V0 to V5 on a real gateway** | reader and ACK chains, strictly in order, one day |

**How many sessions.** Three at the same time: one `frontend-designer` on the map chain, one implementer on the backend chain (T601, T602, T603, T604, T621), one floating implementer (T600, T620, T610, then the three hardware branches, which are written and reviewed while they wait for the bench). The limit is the gates: a smoke run and a breaker run per PR, a security review for eight of the fifteen tasks, and one bench session for stage H.

**Rollback of the wave.** No schema or data change in any task; every PR is undone with `git revert -m 1 <merge commit>`, newest first inside a chain. The order per plan is in each plan's risk section; T611 to T613 are reverted together.

**The critical path** is T547, T602, T604, T621, T690 on the backend, and it starts with two things this wave does not control: T547 has no commit yet, and O4 is not answered. Without them stage A and B and the whole frontend plan still run. The hardware stage is outside the path by design: the wave closes without T611 to T613, with R-06 and R-07 still open and the three `xfail` tests still in place.

## 4. Expected conflicts

| File | Tasks | Kind | Resolution |
|------|-------|------|------------|
| `backend/hardware_reader/reader.py` | T547 (edits), T602 (moves it and puts an alias at the old path) | git does not see a rename when the old path keeps a file | T547 first. If T602 is merged first by mistake, the T547 branch redoes its `reader.py` edit in `modules/gateway/infrastructure/reader.py` by hand and takes the alias file unchanged |
| `backend/main.py` | T602 (router import and mount), T603 (two reader blocks), T620 (clean-up loop and three imports) | different blocks | keep every deletion; rerun `test_main_names_no_reader` and `test_main_holds_no_cleanup` |
| `backend/modules/registry.py` | T602 | one import and one name | `gateway` last in the tuple |
| `backend/tests/architecture/importlinter.toml`, `approved_additions.py` | T602 (a new contract; `backend.modules.gateway` appended to every other `source_modules`), T603 and T620 (one `forbidden_modules` line each) | different contracts | take both sides, then `regen.py --check` and `check_boundary_contracts` (it names a missing private child) |
| `backend/tests/architecture/allowlist.json`, `approved_additions.py` | T620 (one `sql_writes` row), T621 (four `module_edges` rows, four approvals out, two in), T690 (`completed_step`) | rows of different keys | keep both; the exact-match tests and `regen.py --check` name a stale or missing row |
| `backend/modules/gateway/infrastructure/hid_reader.py`, `frozen_hashes.py` | T611, T612 | the same function and its literal | strictly in order; the literal is regenerated, never merged by hand |
| `tools/smoke.py`, `test_smoke_script.py`, `docs/SMOKE.md` | T602, T621 | adjacent `self.step(...)` lines and table rows | keep both, letters k and l |
| `frontend/src/views/MapView.vue`, `useMap.js`, `modules/tracking/index.js`, `i18n/en.js`, `bg.js` | the map chain | ordered chain | one session at a time |
| `frontend/src/architecture.allowlist.json` | T590 (`completed_step` 1 to 2), T690 (to 3) | the same line | T590 first; T690 merges `upstream/develop` |
| `backend/main.py`, `MapView.vue` | this wave against the owner's `main` to `develop` merge | outside the wave | merge `upstream/develop` into the open branch, rerun its DoD and the smoke |

## 5. Reviewers per task

| Reviewers | Tasks |
|-----------|-------|
| breaker + security-reviewer | T602, T603, T604 (`routers/**`, `main.py`, `hardware_reader/**`), T611, T612, T613 (`hardware_reader/**`), T620 (`main.py`, deletion of personal data), T621 (`routers/**`) |
| breaker | T600, T601, T610, T630, T631, T632, T690 |
| ef-migration-reviewer | none: the wave has no migration |
| hardware validation (Kiril Penev) | V0 for T602, T603, T604 (before the release, or before each merge if O4 is no); T611 (V0, V1, V1b, V3), T612 (V0, V2), T613 (V0, V4, V4b), the sum (V5) |
| manual look at the page | T621 (test mode on the dev stack), T630, T631, T632 |

## 6. State after the wave

- Backend: `backend/modules/{fire,gateway,settings,sos,tracking,weather}/`; `main.py` mounts no router of these six, starts no reader and no clean-up; `backend/hardware_reader/*` and `backend/routers/hardware_reader.py` are aliases until step 5; the simulation feeds `gateway.api`; no allowlist entry says step 3.
- Hardware path: with T611 to T613 merged, a frame is acknowledged only when stored (or for one of the two named reasons, logged), an unknown device gets no ACK, position, SOS and notifications are one transaction, an SOS without any fix opens its alert, and R-06 and R-07 can be closed by the architecture owner. Without them the path behaves exactly as on `d174ce3` and the three `xfail` tests say so.
- Frontend: `src/modules/gateway/`; `MapView.vue` holds the shell wiring, the toolbar, HQ and repeater placement and measuring; `useMap.js` holds the basemaps, the graticule, measuring, the repeater layer and the weather tile layer (and the tracker layers if T632 did not run).
- Not done on purpose: `fire` reading positions through a `tracking.api` read model; the Cyrillic `А` decode gap of PROTOCOL.md; a store timeout for a hanging database (it blocks every device, as today); `EventID` in `location_events` (needed so a retransmission after a restart, or a late copy of an older event, is not stored twice); a rate limit for the log line of an unknown device; range checks in the parser; the backends of `people`, `teams`, `devices` and the outbox (step 4); `identity`, `reporting`, `maps`, `simulation` and the removal of the aliases (step 5).

## 7. Open questions, by addressee

For each: what it blocks and the default this wave takes when nobody answers.

**To the maintainer (Kiril Iliev)**

| # | Question | Blocks | Default |
|---|----------|--------|---------|
| M1 | T547 has no commit yet and edits `reader.py` and `routers/test.py`. Does it merge before T602 and T621? | T602, T621 and everything behind them | yes: both wait for it. If it will take long, say so: T602 can go first and T547 then works in the moved file |
| M2 | Which three tasks of wave 2 got `0 stale line(s) removed` from `regen.py`? The tool was tried on `d174ce3` with three kinds of stale TOML line and removed each; it never looked at `allowlist.json` or the approvals. | nothing (T600 adds the JSON part either way) | T600 as planned; if a task deleted only TOML lines, its case is added to T600's tests |
| M3 | Retention and the fire clean-up leave `main.py` now (spec section 6) or in step 5 (wave 2 overview, item 9)? Its allowlist row says `until: 5`, so step 3 does not depend on it. | T620 | now |
| M4 | The tracker panel and layers (T631, T632) in this wave? | T631, T632 | T631 yes; T632 last and droppable |
| M5 | Does `completed_step` become 3 when the allowlist debt of step 3 is gone, although the hardware fix may still wait for the bench? | T690 | yes; T690 reports the state of T611 to T613 and the `xfail` count |
| M6 | The dead serial attempt in `lifespan` (`reader.run` is inside a string, so every boot logs `Serial reader not started`) is dropped by T603. | nothing | drop the attempt, leave the string |
| M7 | Wave 2's T590 is not merged; the frontend allowlist still says `completed_step: 1`. | T690 | T590 runs first; T690 needs it |
| M8 | After T602 the kit's `.claude/protected-paths.txt` should also name `bee-with-me/backend/modules/gateway/**` (decode and ACK now live there). The agent cannot edit the kit. | nothing; the hardware PRs lose the path guard until it is done | the maintainer adds the line when T602 is merged |
| M9 | On Linux, what does `python -c "import mgrs; mgrs.MGRS().toMGRS(42.0, float('nan'))"` do: raise, return, or end the process? On Windows it raises `OSError` (an access violation). | nothing in this wave: T611 keeps `nan` and infinite coordinates away from the parser on every platform | run it once in the Linux CI image or on a Linux bench and write the result in T611's PR; if the process dies, the field check of T611 is the only guard and must not be removed |

**To the owner (kvelev)**

| # | Question | Blocks | Default |
|---|----------|--------|---------|
| O1 | Who runs the validation protocol, on which gateway, in which window (spec section 9, question 2)? | T611, T612, T613 and the release | Kiril Penev on his bench; nothing of stage H is merged before |
| O2 | The policy table (hardware plan, section 1.1). Four lines are decisions: no ACK for an unknown or inactive device; ACK for a no-fix frame without SOS that is dropped for lack of an earlier fix; ACK plus an ERROR log for a frame the database can never store; and new behaviour: an SOS in a frame without any fix opens an alert without a position (today that SOS is dropped and acknowledged). R-07 asks for exactly this decision. | T612, T613 | the table as written, for implementation only: T612 is merged only after the owner and the device maker confirmed it (O2 and the numbers of V2) |
| O3 | `docs/PROTOCOL.md` after the move: see the text proposals of section 8. | nothing | the file is not edited by this wave |
| O4 | The split the spec allows: may the move (T602, T603, T604: no decode, filter or ACK line changes, proven by T601) be merged without a run on the real gateway, with check V0 required before the next release instead? | the merge of T602, T603, T604 and of T621 and T690 behind them | none: without an answer the three stay open PRs. Recommended answer: yes |
| O5 | `.github/CODEOWNERS` has `/backend/hardware_reader/ @kvelev`; after T602 the code is in `/backend/modules/gateway/`. | nothing (the `*` rule still names the same owner) | the owner adds the line; T602's PR body asks for it |

**To the device maker (Kiril Penev)**

| # | Question | Blocks | Default |
|---|----------|--------|---------|
| P1 | How often and how many times does a bee or a repeater retransmit a frame that got no Cmd=1, how long does it wait for the ACK, when does it give up, and does an unacknowledged frame hold back the device's later frames? | T612 (battery and air time of a device that is never acknowledged); V3 (needs a retry interval under 15 seconds); the store-timeout decision | measured in V2 and V1b, then decided |
| P2 | Is there, or could there be, a negative acknowledgement ("received, not accepted")? It would replace "ACK and log" for `REJECTED`. | nothing now | none assumed |
| P3 | Does `EventID` restart after a device reboot? A restarted counter inside the 15 second window would be dropped as a duplicate and acknowledged. | nothing now (today's behaviour) | unchanged; recorded as a risk |
| P4 | The thin payload question of wave 2 (does anything outside the browser read names or phones from `/ws`) is still open; T547 ships with `LIVE_PERSONAL_FIELDS` true until it is answered. | switching the setting off | stays on |
| P5 | The Cyrillic `А` in `GNSSStatus` (PROTOCOL.md, "known gap"): does any firmware send it? | nothing in this wave | not fixed; needs a decode change and hardware |
| P6 | Can a real device send a field outside the ranges the database stores (`MsgId` above 32767, `Course` above 32767) or a latitude the MGRS conversion refuses (above 90, `nan`)? | nothing; a database-range frame is `REJECTED` after T611, a latitude the parser cannot convert is dropped with a WARNING and no ACK (T611's guard around `parse_frame`); today both tear the reader down | no range check is added to the parser in this wave (T601 pins it) |

**To the architecture owner** (text proposals, not edited by this wave)

| # | Proposal | Default |
|---|----------|---------|
| A1 | modular-monolith.md 4.1: `gateway` reads `devices` (by serial number and type) through SQL declared in `reads_tables` until `devices.api` exists in step 4. | as proposed |
| A2 | modular-monolith.md 4.2: `simulation` keeps calling `tracking.api` and `sos.api` for the reset of demo data until step 5 (two `module_edges` rows, `until: 5`); it feeds frames only through `gateway.api`. | as proposed |
| A3 | modular-monolith.md 5.1: add the outcome and ACK table of the hardware plan; state that the transaction is opened by the gateway handler and that `serial_status` is a direct broadcast, not a forwarded channel (also `api-contracts.md`, section 3). | as proposed |
| A4 | risk-register.md: R-06 and R-07 to "Mitigated" when T611 to T613 are merged with their validation tables; new risks: a duplicate row after a restart or for a late copy of an older event (the window is in memory and holds one event per device); one hanging store blocks every device; an oversized `location_update` is stored but not sent live. | after stage H |
| A5 | An ADR for the ACK policy (which frames are acknowledged and why), so the table has a home outside a plan. | propose after O2 and P1 are answered |

## 8. Text proposals for files this wave does not edit

- `docs/PROTOCOL.md` (owner): "Hardware topology" names `hardware_reader/hid_reader.py` and `hardware_reader/reader.py`; after T602 these are aliases of `backend/modules/gateway/infrastructure/*` and the parser is `backend/modules/gateway/domain/parser.py`. The same paragraph names a helper `_dsn` in `reader.py`; the code has `_device_row`. The section "Cmd=1" says the ACK is sent after a frame has been handled successfully, so a frame that fails to persist is left unacknowledged; on `d174ce3` that is not what the code does (the event is marked seen before the store and an unknown device is acknowledged: R-06, R-07) and it becomes true with T611 to T613. Suggested addition there: the outcome table of the hardware plan. The section on `GNSSStatus = V` says a no-fix frame without an earlier fix is dropped; after T613 that holds only for a frame without SOS.
- `.github/CODEOWNERS` (owner) and `.claude/protected-paths.txt` (maintainer): add `backend/modules/gateway/` (O5, M8).
- `docs/SMOKE.md`, section "Not checked": after T621 the handler of the hardware reader **is** exercised (steps e and l go through `gateway.api`); the USB device, the duplicate filter and the ACK still are not. T621 edits this file itself (it is not owner-protected); listed here so the owner sees the changed claim.
- `README.md`, `CHANGELOG.md`, `todo.md`: nothing in this wave needs an edit; the release notes of the release that carries stage H should say "the gateway acknowledges a frame only after it is stored" and "an SOS sent before the first GNSS fix raises an alarm".

## 9. What the briefing said and the code says differently (`d174ce3`)

- T547 has no commit yet: its branch `feature/vs-2-t547` points at `d174ce3`; there is no typed model and no `LIVE_PERSONAL_FIELDS` on `upstream/develop`.
- Not only T548 and T549 are left of wave 2: T545 (the SOS toast is still `components/SOSToast.vue`) and T590 (the closing check; the frontend allowlist still says step 1) are not merged either.
- The "retention in `main.py`" is one loop with four jobs: the position delete and three fire jobs (anonymise alerts, anonymise hotspots, prune). T620 moves all four.
- `main.py` tries to start a serial reader at every boot by importing `reader.run`, which does not exist (the function is inside a string), and logs a warning.
- The three expected-to-fail tests are strict `xfail`s in `test_hid_process_frame.py`; two pin the ACK (failed store, unknown device) and the third pins the single transaction.
- `regen.py --remove-stale` could not be made to print a wrong zero for TOML lines; it has no code for `allowlist.json` or the approvals.
- Found while reviewing, not in the briefing: a no-fix frame without an earlier fix is dropped and acknowledged even when it carries SOS (the alarm is lost today).
- Confirmed as briefed: the five backend modules, the reader writing through both APIs (T542), 12 `module_edges` rows of which four say `until: 3`, the import allowlist and its ratchet tests.

## 10. What the review round changed

- **Hardware plan.** Store errors are classified: a passing failure gets no ACK, a frame that can never be stored is `REJECTED` (ACK, ERROR log), and no exception but a closed connection leaves `_process_frame` (the first version would have retried a poison frame for ever, or torn the reader down on every copy). The window time is read after the store. An SOS without any fix opens its alert (`ALERT_ONLY`). T611 to T613 merge as one unit, because T611 alone makes one SOS loss silent. The protocol was corrected: V4 uses an interactive `psql`, V3 has a precondition, V4b is new, V2 runs first.
- **Gateway plan.** The pin hashes normalised source text, not `ast.dump` (which differs between the CI's Python and newer ones), keeps import names in the hash and also pins the command numbers and frame classes. The handlers return outcomes already in T604 (the simulation needs them and must not depend on a hardware-gated task), so T610 moves before T604. `gateway.tasks` is added to the boundary contract. The move tasks are no longer called "safe to merge" without the owner's yes (O4).
- **Tracking plan.** Tests the first version called unedited are listed with their edits (`test_main_names_no_fire_internals`, the loop-driving cases of the anonymise tests, a smoke-shape assertion, two `db`-marked simulation tests). `seed` returns the columns the new path reads. A start without a reset sends a falling edge first, or the simulated SOS would stay silent. The no-fix 400 comes from the handler's outcome.
- **Frontend plan.** The two text keys keep their names (a snapshot test compares names). `MapView.b66.test.js` is listed. The status is refetched on every tick, because `setup` runs once per page. The 10 second tick stays with the list it sorts and is owned by the view; the list is passed as a ref.
- **Round 2 and 3 (hardware plan).** The parser can raise (the MGRS conversion) before any store, so `parse_frame` is inside the guard. `REJECTED` is exactly the database's class 22 (`DataError`); everything else, including a bare `ValueError`, `TypeError` and `ProgramLimitExceededError` (SQLSTATE 54000: also a full notification queue), is `STORE_FAILED`, so a systematic fault can never acknowledge and drop frames. A duplicate never refreshes the window (an existing test depends on it). T613 edits `delegates_helper.py` (a transaction mock) and the fire manifest tests are edited in T620. T611 uses a temporary ACK rule so an unknown device keeps being acknowledged until T612.
- **Round 4.** T604's test of the unchanged ACK no longer pins the temporary behaviour and is deleted in T611. A `nan` or infinite coordinate is kept away from the parser in T611, because the native MGRS fault is an `OSError` only on Windows (M9, P6). `REJECTED` is narrowed again: a client-side `DataError` counts only when its cause is an `OverflowError`, so a type bug cannot acknowledge and drop every frame. Log lines print `outcome.value`. T613 tests a failure at commit. The `Repeated ... ignored` lines stay, `ALERT_ONLY` does not change Resolve, and a `REJECTED` frame with SOS loses the alert (accepted, written in the hardware plan's risks), except the one case that was a regression: an oversized `location_update` is no longer sent at all (T613: `publish_position` returns `False`, the position and the alert are committed). V5 counts one decision line per frame. T632 has a test for the failure note.
- **Overview.** Chains for the gateway module files, the gateway tests, the TOML and the tracking API were missing; T690 needs T590.

---

### Task 690: closing check of wave 3 on `develop`

**risk:** normal
**owner:** implementer
**hardware:** safe
**Files:**
- Create: `backend/tests/modules/core/test_wave3_state.py`
- Create: `frontend/src/modules/wave3.test.js`
- Modify: `backend/tests/architecture/allowlist.json` (`completed_step`: 3), `frontend/src/architecture.allowlist.json` (`completed_step`: 3)

**Interfaces:**
- Consumes: the merged result of T600 to T604, T610, T620, T621, T630 and T631, and wave 2's T590 (it sets the frontend `completed_step` to 2 and pins wave 2; this task does not replace it). The state of T611, T612, T613 and T632 is reported, not asserted.
- Produces: two test files that pin what wave 3 reached, with membership and lower bounds only, so step 4 adds modules and removes allowlist rows without editing them.

- [ ] **Step 1: Merge check.** On a branch off the current `upstream/develop`, confirm with `git log --oneline upstream/develop` that the merge commits of T590, T600 to T604, T610, T620, T621, T630 and T631 are present; a missing one stops this task and is reported. Write into the PR body whether T611, T612, T613 and T632 are merged and the output of `git grep -c "pytest.mark.xfail" backend/tests/modules/gateway/test_hid_process_frame.py`; with a count above zero add the line "R-06 and R-07 open: the hardware fix waits for validation".
- [ ] **Step 2: Write the tests.** Backend, tagged `T690`: `test_gateway_is_a_module` (`'gateway'` is in `[m.name for m in backend.modules.MODULES]`; `completed_step >= 3`); `test_the_old_reader_paths_are_aliases` (each of the four old dotted paths imports as a module whose `__name__` starts with `backend.modules.gateway`); `test_no_allowlist_entry_is_due_at_step_3` (no `module_edges` or `sql_writes` row has `until <= 3`; no line of `importlinter.toml` ends with `# until step 3`, `# until step 2` or `# until step 1`); `test_the_simulation_writes_through_the_gateway` (the import graph of `backend.routers.test` has `backend.modules.gateway.api` and neither `backend.modules.tracking.api` nor `backend.modules.sos.api`); `test_the_reader_and_two_cleanups_are_module_tasks` (the task names started for `MODULES` include `gateway.run_hid_reader`, `tracking.cleanup_positions`, `fire.cleanup_fire_data`); `test_the_hardware_pin_is_complete` (`set(frozen_hashes.FROZEN) == set(frozen_hashes.PINNED)` and `current_hashes() == FROZEN`). Frontend, each `[T690]`: `gateway is a module and handles serial_status`; `the tracker panel is a tracking panel`; `MapView imports no gateway status call` (the text of `views/MapView.vue` has no `getSerialStatus`); `no manifest reaches OpenLayers`; `the frontend step is recorded` (`completed_step >= 3`).
- [ ] **Step 3: Run, expect FAIL, then record the step.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\core\test_wave3_state.py -q`. Expected: FAIL on `completed_step >= 3` only. Set `completed_step` to 3 in both allowlist files and run the architecture suites; a test that now reports an overdue entry names what is still left of step 3 and stops the task.
- [ ] **Step 4: Run the full suites, the build and the smoke.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests -q`. Expected: PASS. Run: `cd bee-with-me\frontend; npm test; npm run build`. Expected: PASS and a clean build. Then `python tools/smoke.py`: every step PASS, including e, k and l. Write into the PR body: the three allowlist counts (the commands of the gateway plan, section 2), the entry chunk size, and the questions of section 7 that are still open.
- [ ] **Step 5: Commit** `test(architecture): T690 pin the state after wave 3`.

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\core\test_wave3_state.py backend\tests\architecture -q`
- `cd bee-with-me\frontend; npm test -- src/modules/wave3.test.js src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`
