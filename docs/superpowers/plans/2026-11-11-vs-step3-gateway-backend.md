# Vertical slices, step 3: the `gateway` module (move, no behaviour change) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `backend/hardware_reader/` and `backend/routers/hardware_reader.py` the backend module `backend/modules/gateway/`, start the HID reader from the module manifest, and give the simulation a door into the gateway (`gateway.api`), all without changing one line of decoding, duplicate filtering or acknowledging.

**Architecture:** The three reader files move with `git mv` into `domain/` (the pure parser) and `infrastructure/` (HID reader, reader handlers); the old paths become `sys.modules` aliases, as `backend/fire/*` did in wave 2, so every existing test and patch keeps working. A frozen-function test, written first and run unedited after the move, is the proof that decode, duplicate filter and ACK did not change. The fixes of the hardware path (R-06, ES-23) are **not** in this plan: they are the next plan and wait for a real gateway.

**Tech Stack:** Python 3.11+, FastAPI, asyncpg, hidapi (lazy import inside `run`), import-linter, pytest. No new dependency.

**Spec:** [`docs/superpowers/specs/2026-10-31-vertical-slices-programme-design.md`](../specs/2026-10-31-vertical-slices-programme-design.md) sections 5 ("Step 3"), 6, 7, 9; `Architecture/application/modular-monolith.md` sections 3, 4.1, 4.2, 5.1, 9; ADR 17, 19; `docs/PROTOCOL.md` (authoritative, owner-written, not edited). Overview: [`2026-11-11-vs-wave3-overview.md`](2026-11-11-vs-wave3-overview.md).

**Base:** `upstream/develop` at `d174ce3` (PR #150, T542 merged; checked on 2026-11-11 with `git fetch upstream; git log --oneline -1 upstream/develop`). Execution branches: `feature/vs-3-<task>` off `develop`, one PR per task.

## Global Constraints

- Decisions that are not reopened: base branch `upstream/develop`; kernel `backend/core/` and `frontend/src/platform/`; `main.py`, `db/migrate.py`, `version.py` stay; old import paths are `sys.modules` aliases until step 5 (never `import *`); auth is the loader's default; WebSocket security is not implemented; behaviour does not change; no migration (numbers `0008` and `0009` are reserved by step 4).
- **No task of this plan edits a line of decode, duplicate filter or ACK.** These are, in the parser, the functions `crc16`, `_strip_and_verify`, `_parse_bee`, `_parse_repeater`, `make_confirm`, `parse_frame` and the classes `RLCommands`, `BeeFrame`, `RepeaterFrame`; in the HID reader, the functions `_process_frame`, `_send_data`, `run` and the constants `EVENT_TIMEOUT`, `HID_BUFFER_SIZE`, `READ_INTERVAL`, `RECONNECT_DELAY`. T601 pins them; a diff that touches one of them is a finding, whatever the tests say. The one allowed difference is the number of leading dots of a relative import inside `run` (the file moves two folders down in T602); T601 normalises exactly that and nothing else.
- **Hardware:** no task of this plan changes decode, duplicate filter or ACK, so each is **safe to implement and review without hardware**; T600 and T601 are merged at once. T602, T603 and T604 change which code starts and runs the reader on a field machine. The spec's constraint table says step 3 is validated on a real gateway before merge, and it lets the owner split the step into "move only" and "fix". This plan proposes the split: because field machines run tagged releases (`develop` deploys only to bee-dev, which has no gateway), the real-hardware check of the move, V0 of the hardware plan, is a **release gate** instead of a merge gate. That needs the owner's yes (overview, O4). Until it is given, T602 to T604 are implemented, reviewed and kept as open PRs; with a no, V0 is run on each branch before its merge.
- Every task that adds a route or changes how the live path starts adds or keeps a step in `tools/smoke.py` (T602 adds step k).
- Task numbers T600 to T604; `git grep -nE "\bT6[0-9]{2}\b"` on `d174ce3` prints nothing. Tags: pytest `@pytest.mark.Trait("Task", "T6xx")`.
- Logging: `logger.info('... %s', value)`. Freshness is judged on `received_at`.

## Review Focus

1. The reader stops running without anyone noticing (BP-01): the manifest starts `gateway.run_hid_reader`; a test proves the task is created, named and logged when it crashes (T603). A module list that fails to import now stops the backend loudly instead of logging "HID reader not started"; that is intended and stated in the PR.
2. A moved file silently changed a decode line: T601 hashes the frozen functions before the move and after it (T602); the hash literals are never edited in this plan. A wrong dot count in a moved lazy import would only show on a real run, so T602 calls the real `_vid_pid`, `_connect_kwargs`, `_port_and_baud` and `_broadcast_status` once, unpatched.
3. A test patches a name on the old path and tests nothing: aliases are the module object itself (`sys.modules` swap), so `monkeypatch.setattr(hid_reader, 'time', ...)` still reaches the module state (`bee_last_events`).
4. The status route loses its login by moving: `GET /api/serial/status` answers 401 without a token on the real app (T602).
5. The simulated frame is not a real frame: `encode_bee_frame` output must pass `parse_frame` unchanged and round-trip every field the handler reads (T604).

---

## 1. Design

### 1.1 Target layout and what moves

| Today (`d174ce3`) | After | Task |
|-------------------|-------|------|
| `backend/hardware_reader/parser.py` | `backend/modules/gateway/domain/parser.py`; the old path is an alias | T602 |
| `backend/hardware_reader/hid_reader.py` | `backend/modules/gateway/infrastructure/hid_reader.py`; alias | T602 |
| `backend/hardware_reader/reader.py` | `backend/modules/gateway/infrastructure/reader.py`; alias | T602 |
| `backend/routers/hardware_reader.py` | `backend/modules/gateway/http.py`; alias | T602 |
| `main.py`: the two `try:` blocks of `lifespan` that import `reader.run` and `hid_reader.run` | `backend/modules/gateway/tasks.py` and the manifest field `tasks` | T603 |
| (none) | `backend/modules/gateway/api.py` (`store_frame`) and `domain/encode.py` (`encode_bee_frame`) | T604 |

The alias file of each old path is three lines, the form of `backend/fire/service.py`:

```python
"""Old import path of backend.modules.gateway.infrastructure.hid_reader, kept until step 5."""
import sys

from ..modules.gateway.infrastructure import hid_reader as _impl

sys.modules[__name__] = _impl   # the old name IS the new module: patches and module state stay shared
```

Imports inside the moved files change from `..config`, `..ws`, `..core.database` to the kernel paths (`....core.config`, `....core.ws`, `....core.database`); that removes the four `backend.hardware_reader.* -> backend.config | backend.ws` shim lines. They sit in `_vid_pid`, `_broadcast_status`, `_connect_kwargs`, `_port_and_baud` and one `import` line inside `run`; T601 normalises imports before hashing, so this is allowed and nothing else is.

### 1.2 Manifest

`name='gateway'`, `owns_tables=()`, `reads_tables=('devices',)` (the reader reads `devices` by serial number and type; the `devices` module does not exist before step 4, so the read stays SQL in the gateway repository and `devices.api` replaces it in step 4), `depends_on=('tracking', 'sos')`, `router=http.router` (prefix `/api/serial`, one route), `tasks=()` in T602 and `tasks=(tasks.run_hid_reader,)` from T603, `live_messages=()` (`serial_status` is a direct `manager.broadcast`, not a `pg_notify` channel, and `check_manifest_wiring` accepts only names in `core.ws.FORWARDED_CHANNELS`). The registry becomes `(fire, settings, weather, tracking, sos, gateway)`.

### 1.3 Allowlist arithmetic (counts are read with the commands of section 2)

| Entries today | What happens | Task |
|---------------|--------------|------|
| `importlinter.toml`, contract "legacy shims are not imported by production code": four lines `backend.hardware_reader.{hid_reader,reader} -> backend.{config,ws}` | deleted (the moved files import the kernel) | T602 |
| new contract `boundary-gateway` (`forbidden`, same shape as `boundary-tracking`): the aliases of the three files and of the router import private children | four alias lines `# until step 5`, each with an approval | T602 |
| `allowlist.json`: no `sql_writes` row mentions `hardware_reader` since T542 | nothing | none |
| `module_edges`: no row (gateway to tracking and sos is an allowed edge) | nothing | none |

`completed_step` stays 2; wave 3 closes it in T690.

## 2. File map and who else touches each file (as of `d174ce3`)

Commands used: `git grep -nE "hardware_reader|hid_reader|_handle_bee|_handle_repeater" -- backend tools start.ps1 start.sh scripts deploy ":!backend/hardware_reader"`; the allowlist counts: `.venv\Scripts\python backend\tests\architecture\regen.py --print-violations` (lines per contract) and `.venv\Scripts\python -c "import json;d=json.load(open('backend/tests/architecture/allowlist.json'));print({k:len(v) for k,v in d.items() if isinstance(v,list)})"`.

| File | This plan | Also read or written by |
|------|-----------|-------------------------|
| `backend/hardware_reader/reader.py`, `hid_reader.py`, `parser.py` | T601 (reads), T602 (becomes aliases), T604 (`reader.py` gets one keyword) | T547 of wave 2 (the payload arguments in `_handle_bee`; **must merge before T602**), hardware plan T611 to T613 |
| `backend/main.py`, `modules/registry.py`, `tests/architecture/importlinter.toml`, `approved_additions.py` (hot) | T602, T603 | wave 2 T547; tracking plan T620, T621 |
| `tools/smoke.py`, `backend/tests/test_smoke_script.py`, `docs/SMOKE.md` (hot) | T602 (step k) | tracking plan T621 (step l) |
| `backend/tests/architecture/regen.py` | T600 | none |
| `backend/tests/architecture/test_module_edges.py` | T603 (one assertion) | none |
| `backend/tests/modules/gateway/*` | T601, T602, T603, T604 add files | hardware plan edits `test_hid_process_frame.py` (removes `xfail`) |
| `backend/tests/modules/core/test_b86_password_not_logged.py`, `backend/tests/modules/fire/test_fire_api.py`, `backend/tests/test_b93_lifespan_shutdown.py` | read-only: they import the old paths and patch `hid_reader.run` | the aliases keep them green unedited |

## 3. Task order, PRs, reviewers, parallel work

| PR | Task | Content | Needs | Owner | Reviewers | Hardware |
|----|------|---------|-------|-------|-----------|----------|
| 1 | T600 | `regen.py` also removes stale `allowlist.json` rows and lists stale approvals | nothing | implementer | breaker | safe |
| 2 | T601 | pin decode, duplicate filter and ACK by hash | nothing | implementer | breaker | safe |
| 3 | T602 | the module: move, aliases, manifest with the status route, contract, smoke step k | T600 (`regen.py --check`), T601; wave 2 T547 merged | implementer | breaker + security-reviewer (`routers/**`, `main.py`, `hardware_reader/**`) | no pinned function changes; V0 (release gate if O4 is yes) |
| 4 | T603 | the HID reader starts from the manifest | T602 | implementer | breaker + security-reviewer (`main.py`, `hardware_reader/**`) | the same |
| 5 | T604 | `gateway.api` (`store_frame`, `parse_frame`, `encode_bee_frame`); the handlers return outcomes | T602; T610 of the hardware plan (the `Outcome` type, pure) | implementer | breaker + security-reviewer (`hardware_reader/**`) | the same |

T600 and T601 start at once and run in parallel. T603 and T604 both follow T602 and share no file with each other (`module.py`, `tasks.py`, `main.py` and the TOML for T603; `api.py`, `reader.py` and `domain/encode.py` for T604), so they may run at the same time.

**PR gate (every PR):** the fire plan's gate of wave 2 (smoke run before the PR, `breaker`, `security-reviewer` where the table says so, `gh pr create` by the human with `--body-file`). T602 to T604 paste the PASS lines of smoke steps e, j and k. No `ef-migration-reviewer`: no migration.

## 4. Risks, rollback, not verified

| Risk | Mitigation |
|------|------------|
| The moved reader no longer starts on a field machine and nobody sees it | T603 tests; V0 of the hardware plan at release time: the log line `HID device opened` and `frames_received` climbing |
| An alias breaks a patch that targets `backend.hardware_reader.hid_reader.<name>` | the alias is the module object; `test_the_old_paths_are_the_module_files` and the unedited gateway tests are the proof |
| `git mv` plus a new file at the old path makes a rename invisible to git, so a branch that edited `reader.py` (T547) conflicts | T547 merges first (chain in the overview); a later branch merges `upstream/develop` |
| A frozen hash fails after the move because of an import line inside a pinned function | the hash normalises `Import` and `ImportFrom` nodes; if a pinned function still differs, stop and report |
| bee-dev gets a broken image | smoke before every PR; `git revert -m 1 <merge>` |

**Rollback.** No schema or data change. Revert newest first: T604, T603, T602 (T603 must not stay when T602 goes), then T601 and T600 (harmless to keep).

**Not verified while planning:** no frame was sent by a real gateway and no browser was opened; the exact text of the three `xfail` reasons was read, not run; the hash values of T601 are produced by the implementer (command in T601), not written here.

## 5. Existing tests

All existing tests stay green without edits, except:

| File | Edit | Kind | Task |
|------|------|------|------|
| `backend/tests/architecture/test_module_edges.py` (`test_the_graph_sees_function_level_and_lazy_imports`) | the assertion that `backend.main` imports `backend.hardware_reader.hid_reader` (a lazy import) is replaced by another existing function-level import, `backend.routers.test` importing `backend.simulation` (`git grep -n "from ..simulation import" backend/routers/test.py` shows it); the test still proves that the graph sees lazy imports | deliberate: the lazy import it named goes in T603 | T603 |
| `backend/tests/modules/gateway/test_gateway_module.py` (`test_manifest`, written in T602) | `tasks == ()` becomes `tasks == (tasks.run_hid_reader,)` | deliberate: T603 adds the task | T603 |
| `backend/tests/modules/gateway/delegates_helper.py` (`run_case`) | gets an optional parameter `call` (default: today's direct call of `reader._handle_bee` and `reader._handle_repeater`) so T604's test can run the same six frames through `gateway.api.store_frame` | new parameter, old behaviour by default | T604 |

`test_hid_process_frame.py`, `test_hid_run.py`, `test_reader_handlers.py`, `test_reader_delegates.py`, `test_parser.py`, `test_b86_password_not_logged.py`, `test_fire_api.py`, `test_b93_lifespan_shutdown.py` and `test_module_edges.py::test_direction_rule_bites` (a pure string test) are not edited.

**Outside the tests, for the humans:** `.github/CODEOWNERS` has the line `/backend/hardware_reader/ @kvelev` and the kit's `.claude/protected-paths.txt` protects the same folder by path. After T602 that folder holds three-line aliases and the real code is in `backend/modules/gateway/`. Both files are outside an agent's write scope (`.github/**` is ask-first, the kit file is the kit's own): the PR body of T602 asks the owner and the maintainer to add `/backend/modules/gateway/` to each before T611 is opened.

## 6. Open questions (details in the overview, section 7)

1. **To the maintainer:** T602 waits for T547. If T547 stalls, T602 may port T547's branch instead (default: wait).
2. **To the maintainer and the owner:** the dead serial attempt in `lifespan` (`reader.run` does not exist, it sits inside a string) is dropped by T603 (default: drop the attempt, keep the file's string untouched). Related and not changed: `python -m backend.hardware_reader.hid_reader` runs the alias file after T602, which does nothing; the standalone runner is `python -m backend.modules.gateway.infrastructure.hid_reader` until step 5.
3. **To the architecture owner:** `gateway` reads `devices` by SQL until step 4 (`reads_tables`); text proposal for modular-monolith.md 4.1 in the overview.

---

### Task 600: `regen.py` also removes stale `allowlist.json` rows and lists stale approvals

**risk:** normal
**owner:** implementer
**hardware:** safe
**Files:**
- Modify: `backend/tests/architecture/regen.py`
- Create: `backend/tests/architecture/test_regen_json.py`

**Why first.** In three tasks of wave 2 `regen.py --remove-stale` printed `0 stale line(s) removed` while rows had to go, and the rows were deleted by hand. The tool reads `importlinter.toml` only: its docstring and `remove_stale` never open `allowlist.json` or `approved_additions.py`, which hold the `sql_writes` rows, the `module_edges` rows and their approvals; the exact-match tests (`test_real_writes_match_the_allowlist_exactly`, `test_real_module_edges_match_the_allowlist_exactly`, `test_every_approval_is_still_in_its_file`) report such a row, nothing deletes it. For the TOML lines the tool was tried on 2026-11-11 with a stale line whose importer still exists, one whose importer is gone and one that is live only in an older checkout: all three were handled correctly, so the zero is not a defect of the TOML part. The three tasks are not named in the repository; the implementer asks the maintainer which they were and, if one deleted only TOML lines and still got zero, adds that case to the tests.

**Interfaces:**
- Consumes: `rules.sql_violations(writes)`, `sql_scan.scan_writes(root)`, `rules.module_edge_violations(imports)`, the grimp graph built as in `test_module_edges._graph`, `approved_additions.APPROVED`, `test_ratchet.entries(text, kind)`.
- Produces in `regen.py`: `stale_sql_rows(allowlist: dict, real: set[tuple[str, str, str]]) -> list[dict]` (rows of `sql_writes` whose `(file, table, verb)` is not in `real`); `stale_edge_rows(allowlist: dict, real: set[tuple[str, str]]) -> list[dict]` (rows of `module_edges` whose `(from, to)` is not in `real`); `stale_approvals(approved: dict[str, dict[str, str]], present: dict[str, set[str]]) -> list[tuple[str, str]]` (file and entry of an approval whose entry is not in its file).
- Produces the behaviour: `--remove-stale` removes stale TOML lines as today **and** stale JSON rows (the file is rewritten with `indent=2`, the same key order and one trailing newline) and prints `toml: N, allowlist.json: N, approvals to delete by hand: N`, listing each approval; it never edits `approved_additions.py` (a Python literal is not rewritten by a script) and never adds anything. `--check` prints the same lines, writes nothing and returns 1 when any is stale, 0 otherwise.

- [ ] **Step 1: Write the failing tests**, tagged `T600`, in `test_regen_json.py` (a `tmp_path` copy of a small allowlist and TOML, the real scans replaced by passed-in sets): `test_a_stale_sql_row_is_removed_and_a_live_one_kept`; `test_a_stale_edge_row_is_removed`; `test_check_mode_writes_nothing_and_returns_1`; `test_check_mode_returns_0_when_nothing_is_stale`; `test_stale_approvals_are_listed_and_the_file_is_not_edited`; `test_the_json_file_keeps_its_key_order_and_final_newline`; `test_toml_behaviour_is_unchanged` (the existing `test_remove_stale_deletes_only_stale_lines_and_adds_none` still passes; the new function adds nothing).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\architecture\test_regen_json.py -q`. Expected: FAIL with `AttributeError: module 'backend.tests.architecture.regen' has no attribute 'stale_sql_rows'`.
- [ ] **Step 3: Implement** the three functions, the JSON rewrite and `--check` (a third option of the existing mutually exclusive group).
- [ ] **Step 4: Run** the new tests and the architecture suite, then the real tool on the real tree. Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\architecture -q`. Expected: PASS. Run: `cd bee-with-me; .venv\Scripts\python backend\tests\architecture\regen.py --check`. Expected: `toml: 0, allowlist.json: 0, approvals to delete by hand: 0` and exit code 0 (the tree on `develop` is exact); if any count is not 0, stop and report it: it is a stale row or approval that is already on `develop`.
- [ ] **Step 5: Commit** `test(architecture): T600 regen removes stale allowlist.json rows and lists stale approvals`.

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\architecture -q`
- `cd bee-with-me; .venv\Scripts\python backend\tests\architecture\regen.py --check`

### Task 601: pin decode, duplicate filter and ACK by hash

**risk:** normal
**owner:** implementer
**hardware:** safe (it only reads code); every later change of a pinned function waits for hardware
**Files:**
- Create: `backend/tests/modules/gateway/frozen_hashes.py` (the helper and the literals), `backend/tests/modules/gateway/test_frozen_hardware_path.py`

**Interfaces:**
- Produces in `frozen_hashes.py`: `PINNED: tuple[str, ...]`, the names of the Global Constraints as `"parser.<name>"` and `"hid_reader.<name>"`; `FROZEN: dict[str, str]` mapping each to a sha256 hex string; `normalised_text(source: str, node: ast.AST) -> str`; `current_hashes() -> dict[str, str]`; `python backend\tests\modules\gateway\frozen_hashes.py` prints the dictionary as Python source.
- **The hash is taken over text, not over `ast.dump`** (`ast.dump` differs between Python 3.11, which CI runs, and newer interpreters, so a literal made on one would be red on the other). `ast` is used only to find a definition's first and last line (`lineno`, `end_lineno`, decorators included; for a constant, its assignment statement). `normalised_text` takes those lines, removes the common indentation (`textwrap.dedent`), drops blank lines and lines that hold only a comment, strips trailing whitespace, and rewrites a line that starts with `from .` (tested after the common indentation was removed and the line's own `lstrip()`, because the import inside `run` is indented) so that its leading dots become one dot. Nothing else is normalised: an edited inline comment or a renamed import changes the hash on purpose.
- `current_hashes()` reads the two files as UTF-8 text from the first path that exists of `backend/modules/gateway/domain/parser.py` and `backend/hardware_reader/parser.py` (the same pair for `hid_reader.py`, under `infrastructure/`), skipping a file that is an alias (its text contains `sys.modules[__name__]`). It imports nothing from `backend`, so it works before and after the move and on any interpreter.
- Produces: the literals in `FROZEN`, printed by that command on a checkout of `upstream/develop` and pasted in; they are never written by hand. The PR body says which Python version printed them; the CI run of the PR (Python 3.11) is the proof that the other interpreter prints the same.

- [ ] **Step 1: Write the test**, tagged `T601`, in `test_frozen_hardware_path.py`: `test_decode_duplicate_filter_and_ack_are_unchanged` (`current_hashes() == FROZEN`, and the failure message says which names differ and "a change here must be validated on a real gateway: see docs/superpowers/plans/2026-11-11-vs-step3-hardware-path.md section 2"); `test_normalising_ignores_an_import_level_blank_lines_and_comment_lines_and_nothing_else` (two toy functions that differ only in `from ..x import y` versus `from ....x import y`, in a blank line and in a comment-only line have equal hashes; two that differ in one operand, in the imported name or in the indentation of one statement do not); `test_every_pinned_name_exists_and_is_frozen` (`set(FROZEN) == set(PINNED)`, and a name missing in the source is a failure, so a rename cannot drop a pin silently); `test_a_changed_ack_command_number_is_seen` (the text of `RLCommands` with `CONFIRM = 2` hashes differently).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\gateway\test_frozen_hardware_path.py -q`. Expected: FAIL with `ModuleNotFoundError: No module named 'backend.tests.modules.gateway.frozen_hashes'`.
- [ ] **Step 3: Implement** the helper, run `.venv\Scripts\python backend\tests\modules\gateway\frozen_hashes.py` on a checkout of `upstream/develop` and paste the printed dictionary as `FROZEN`.
- [ ] **Step 4: Run.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\gateway -q`. Expected: PASS (the three `xfail` tests of `test_hid_process_frame.py` still XFAIL, strict).
- [ ] **Step 5: Commit** `test(gateway): T601 pin decode, duplicate filter and ACK by hash`. PR body: the command, and the sentence "every later PR that edits a pinned function updates `FROZEN` on purpose and is a hardware PR".

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\gateway -q`

### Task 602: the `gateway` module: move, aliases, manifest with the status route, contract, smoke step k

**risk:** security
**owner:** implementer
**hardware:** no pinned function changes. Merged without a gateway run only with the owner's yes to O4 (V0 is then a release gate); otherwise after Kiril Penev ran V0 on this branch.
**Files:**
- Move (`git mv`): `backend/hardware_reader/parser.py` to `backend/modules/gateway/domain/parser.py`; `hid_reader.py` and `reader.py` to `backend/modules/gateway/infrastructure/`; `backend/routers/hardware_reader.py` to `backend/modules/gateway/http.py`
- Create: `backend/modules/gateway/{__init__.py, module.py, api.py}` (`api.py` is a docstring in this task), `domain/__init__.py`, `infrastructure/__init__.py`; four alias files at the old paths (`backend/hardware_reader/{parser,hid_reader,reader}.py`, `backend/routers/hardware_reader.py`)
- Modify: `backend/modules/registry.py`, `backend/main.py` (the name `hardware_reader` leaves the `from .routers import` line and `app.include_router(hardware_reader.router)` is deleted), `backend/tests/architecture/importlinter.toml`, `approved_additions.py`
- Modify: `tools/smoke.py`, `backend/tests/test_smoke_script.py`, `docs/SMOKE.md` (step k)
- Create: `backend/tests/modules/gateway/test_gateway_module.py`

**Interfaces:**
- Consumes: the loader and the direction ratchet of wave 2, `backend.auth.get_current_user`, the manifest of section 1.2, T601.
- Produces the module of section 1.1 and 1.2. `http.py` keeps `router = APIRouter(prefix='/api/serial', tags=['hardware_reader'])` and `serial_status` with today's signature, and still returns `hid_reader.public_status()` through the module attribute `hid_reader` (looked up at call time).
- Produces in `importlinter.toml`: the four shim lines of section 1.3 are gone; contract `boundary-gateway` (`id = "boundary-gateway"`, `name = "module boundary: gateway"` (`check_boundary_contracts` looks a contract up by its name), `type = "forbidden"`, `source_modules` = `rules.LEGACY_SOURCES` plus every other `backend.modules.<name>` on disk, `forbidden_modules` = `http`, `infrastructure`, `domain`, `module` of the module, `allow_indirect_imports = true`, `ignore_imports` = the four alias edges `# until step 5`, each with an approval); `backend.modules.gateway` appended to the `source_modules` of every other `module boundary:` contract.
- Produces in `tools/smoke.py`: step `'k. GET /api/serial/status = 200'`, `needs=('c. admin login + token refresh',)`; `s_serial` expects 200 and a JSON object with the key `connected` (the smoke stack has no gateway, so its value is `false`).

- [ ] **Step 1: Write the failing tests**, tagged `T602`. `test_gateway_module.py`: `test_manifest` (name, no owned table, `reads_tables == ('devices',)`, `depends_on == ('tracking', 'sos')`, `live_messages == ()`, `tasks == ()` at this task, `router is http.router`, no public route); `test_the_old_paths_are_the_module_files` (`sys.modules['backend.hardware_reader.parser'] is backend.modules.gateway.domain.parser`, likewise `hid_reader`, `reader`, and `backend.routers.hardware_reader is backend.modules.gateway.http`); `test_the_status_route_is_served_once_and_needs_a_login` (`GET /api/serial/status` on `backend.main.app` is 401 without a token and 200 with one; exactly one route has that path); `test_main_no_longer_mounts_the_serial_router`; `test_openapi_operation_id_of_the_status_route_is_unchanged` (a literal read from `develop` before the move); `test_the_moved_handlers_keep_their_names` (`reader._handle_bee`, `reader._handle_repeater`, `reader._connect_kwargs`, `hid_reader._process_frame` exist and `hid_reader._handle_bee is reader._handle_bee`); `test_the_lazy_kernel_imports_of_the_moved_files_resolve` (the real, unpatched `hid_reader._vid_pid()` returns two integers, `reader._connect_kwargs()` a dict, `reader._port_and_baud()` a pair, and `await hid_reader._broadcast_status()` reaches a patched `core.ws.manager.broadcast` once: a wrong dot count would be swallowed by its `except Exception`, so the call count is the assertion). In `test_smoke_script.py`: `test_serial_step_passes_on_200_with_connected_key`, `test_serial_step_fails_on_401`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\gateway\test_gateway_module.py -q`. Expected: FAIL with `ModuleNotFoundError: No module named 'backend.modules.gateway'`.
- [ ] **Step 3: Move, alias and wire.** `git mv` the four files, rewrite the relative imports to the kernel paths, write the four aliases, the manifest, the registry line (`gateway_manifest` last), the two `main.py` edits and the smoke step.
- [ ] **Step 4: Extend, then shrink the allowlist** (contract, four alias lines, approvals, `source_modules`, then `regen.py --remove-stale`, which must delete the four shim lines: run `regen.py --check` first and expect `toml: 4`). Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\architecture -q`. Expected: PASS, including `test_every_contract_bites` for `boundary-gateway`.
- [ ] **Step 5: Run the pin and the gateway tests unedited.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_parser.py backend\tests\test_migration_0006.py backend\tests\test_b93_lifespan_shutdown.py backend\tests\test_smoke_script.py -q`. Expected: PASS; `test_decode_duplicate_filter_and_ack_are_unchanged` (T601) passes with its literals untouched.
- [ ] **Step 6: Gate check, not a test.** Git does not show a rename when the old path keeps a file, so compare each moved file with its old content directly. Run, for each of the three pairs (`parser.py` to `domain/parser.py`; `hid_reader.py` and `reader.py` to `infrastructure/`): `cd bee-with-me; git show upstream/develop:backend/hardware_reader/parser.py > $env:TEMP\old_parser.py; git diff --no-index $env:TEMP\old_parser.py backend/modules/gateway/domain/parser.py`. Expected: no difference for the parser; for the two readers only relative-import lines differ. Paste the three outputs into the PR body.
- [ ] **Step 7: Commit** `refactor(gateway): T602 hardware_reader becomes the gateway module behind aliases`. PR body: the aliases and why they are the module itself, the allowlist arithmetic (4 deleted, 4 added), the request about `CODEOWNERS` and `protected-paths.txt` of section 5, the changed logger names (`backend.modules.gateway.infrastructure.hid_reader` and `.reader` instead of `backend.hardware_reader.*`, for anyone who filters the log by name), the hardware note "decode, duplicate filter and ACK are untouched (T601 hashes pass unedited); not run against a real gateway by the agent; the release that contains this PR needs check V0".

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_parser.py backend\tests\test_migration_0006.py backend\tests\test_b93_lifespan_shutdown.py backend\tests\test_smoke_script.py -q`

### Task 603: the HID reader starts from the manifest

**risk:** security
**owner:** implementer
**hardware:** no pinned function changes, but the reader's start moves. Merged without a gateway run only with the owner's yes to O4 (V0 is then a release gate); otherwise after Kiril Penev ran V0 on this branch.
**Files:**
- Create: `backend/modules/gateway/tasks.py`
- Modify: `backend/modules/gateway/module.py` (`tasks`), `backend/main.py` (`lifespan`), `backend/tests/architecture/importlinter.toml` (`backend.modules.gateway.tasks` joins the `forbidden_modules` of `boundary-gateway`: `check_boundary_contracts` compares that list with the private children on disk, as `boundary-fire` shows for `fire.tasks`), `backend/tests/architecture/test_module_edges.py` and `backend/tests/modules/gateway/test_gateway_module.py` (the edits of section 5)
- Create: `backend/tests/modules/gateway/test_gateway_tasks.py`

**Interfaces:**
- Consumes: `core.modules.start_module_tasks` and `stop_module_tasks` (called by `lifespan` since wave 1), T602.
- Produces `tasks.py`: `async def run_hid_reader() -> None` which awaits `hid_reader.run()` looked up on the module at call time (`from .infrastructure import hid_reader` then `await hid_reader.run()`, so a test that patches `hid_reader.run` reaches it, as the fire wrappers do).
- Produces in `main.py`: the `serial_task` and `hid_task` blocks, their `cancel()` lines and the two import lines are gone; the reader is one of `module_tasks`, cancelled and awaited by `stop_module_tasks` before `close_pool`.

- [ ] **Step 1: Write the failing tests**, tagged `T603`: `test_the_manifest_starts_the_hid_reader_task` (`start_module_tasks([gateway_manifest], on_done)` creates a task named `gateway.run_hid_reader` that enters a patched `hid_reader.run`); `test_a_crashing_reader_is_logged_by_name_and_the_app_stays_up` (`hid_reader.run` raises `RuntimeError('boom')`; `main._log_task_failure` logs `gateway.run_hid_reader task crashed: boom`; no exception leaves `lifespan`); `test_the_reader_is_stopped_before_the_pool_closes` (the pattern of fire T503's `test_fire_tasks_are_stopped_before_the_pool_closes`); `test_main_names_no_reader` (the text of `backend/main.py` has none of `hid_reader`, `hardware_reader`, `serial_task`, `hid_task`).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\gateway\test_gateway_tasks.py -q`. Expected: FAIL with `ModuleNotFoundError: No module named 'backend.modules.gateway.tasks'`.
- [ ] **Step 3: Implement** `tasks.py`, the manifest field and the `lifespan` edit; apply the one test edit of section 5.
- [ ] **Step 4: Run.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_b93_lifespan_shutdown.py backend\tests\test_b49.py backend\tests\test_startup_migrations.py -q`. Expected: PASS. Then `python tools/smoke.py`: every step PASS, including e, j and k.
- [ ] **Step 5: Commit** `refactor(gateway): T603 the HID reader is started and stopped by the module manifest`. PR body: the two behaviour differences (the log name of a crash is `gateway.run_hid_reader`; the warning `Serial reader not started: ...` of every boot is gone because `reader.run` does not exist, see open question 2), that a broken gateway import now stops the backend at start instead of logging a warning, and that the reader's `conn.close()` is now awaited at shutdown (before, the task was cancelled and not awaited), so a shutdown against a frozen database waits for it.

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_b93_lifespan_shutdown.py backend\tests\test_b49.py backend\tests\test_startup_migrations.py -q`

### Task 604: `gateway.api` (`store_frame`, `parse_frame`, `encode_bee_frame`) and handlers that say what they did

**risk:** security
**owner:** implementer
**hardware:** no pinned function changes and no statement changes; the handlers gain a return value and one keyword. V0 covers it (release gate if O4 is yes).
**Files:**
- Create: `backend/modules/gateway/domain/encode.py`, `backend/tests/modules/gateway/test_gateway_api.py`
- Modify: `backend/modules/gateway/api.py`, `backend/modules/gateway/infrastructure/reader.py` (`_handle_bee`: the keyword `received_at` and return values; `_handle_repeater`: return values; nothing else)
- Modify: `backend/tests/modules/gateway/delegates_helper.py` (the parameter of section 5)

**Why.** The spec lets the simulation feed `gateway` and never duplicate it. A real frame goes parse, duplicate filter, handler, ACK. The simulation needs the handler without the filter and without the ACK, it must be able to say when the frame was "received" (the stale and lost scenarios store a past `received_at`; freshness is judged on `received_at`), and it must learn whether the frame was stored (its endpoint answers 400 when it was not). The hardware plan needs the same answer for the ACK. So the handlers return an `Outcome` here, once, and nobody acts on it in the reader yet: `_process_frame` is not edited and ignores the value as it ignores `None` today.

**Interfaces:**
- Consumes: T602; `Outcome` (T610 of the hardware plan); `parser.parse_frame`, `parser.crc16`, the handlers of `reader.py`.
- Produces `domain/encode.py` (pure): `encode_bee_frame(*, msg_id: int, dev_sn: int, recorded_at: datetime, gnss_valid: bool, latitude: float, longitude: float, speed_knots: float, course_deg: int, satellites: int, altitude_m: int, sos_active: bool, repeater_mode: bool = False, battery_voltage: float, event_id: int) -> str` returning a complete frame `##30,...@<decimal CRC>` with the 25 fields of PROTOCOL.md in order, the UTC clock fields from `recorded_at` (four-digit year), `A` or `V` for the fix, latitude, longitude, speed and battery written with `repr()` so they parse back to the same float, `Flags = (0x01 if repeater_mode) | (0x02 if sos_active)`, the four RSSI/SNR fields `0`, `HWVer` and `SWVer` `1`; `parse_frame(encode_bee_frame(...))` returns a `BeeFrame` with the same values.
- Produces in `reader.py`: `_handle_bee(frame, conn, received_at=None) -> Outcome` returning `Outcome.UNKNOWN_DEVICE` (no device row), `Outcome.NO_ANCHOR` (no-fix frame without an earlier fix), `Outcome.STORED_NOT_BROADCAST` (inactive person) or `Outcome.STORED`; `received_at = received_at or datetime.now(timezone.utc)` replaces the line `received_at = datetime.now(timezone.utc)`. `_handle_repeater(frame, conn) -> Outcome` returning `UNKNOWN_DEVICE` or `STORED`. No statement, log line or order changes.
- Produces `api.py`: `async def store_frame(conn, frame: BeeFrame | RepeaterFrame, *, received_at: datetime | None = None) -> Outcome` (calls `reader._handle_bee(frame, conn, received_at=received_at)` for a bee and `reader._handle_repeater(frame, conn)` for a repeater, looked up at call time, and returns the handler's outcome; no duplicate filter, no ACK, no transaction of its own); `parse_frame(raw: str)` (pass-through to the parser); `encode_bee_frame` and `Outcome` re-exported.

- [ ] **Step 1: Write the failing tests**, tagged `T604`, in `test_gateway_api.py`: `test_a_frame_round_trips_through_encode_and_parse` (every argument comes back, for a latitude and longitude with seven decimals, a negative longitude, `sos_active`, `repeater_mode`, `gnss_valid=False`, `course_deg=0`); `test_the_encoded_frame_has_a_decimal_crc_over_the_marker_and_payload` (recomputed with `crc16` over the text from `##` up to the `@`); `test_the_encoded_frame_has_25_fields`; `test_the_handlers_return_outcomes` (the fakes of `gateway_fakes.py`: unknown device, no anchor, inactive person, stored; repeater unknown and stored); `test_store_frame_returns_the_handlers_outcome`; `test_store_frame_passes_received_at_to_the_handler` (`_handle_bee` replaced by an `AsyncMock`; the keyword arrives); `test_store_frame_without_received_at_stores_the_server_clock` (the stored `received_at` is within one second of now); `test_store_frame_runs_the_same_statements_as_the_handler` (`delegates_helper.run_case` with `call` set to `store_frame` gives the six literal lists of `test_reader_delegates.py`); `test_store_frame_does_not_touch_the_duplicate_filter` (`hid_reader.bee_last_events` stays empty); `test_process_frame_does_not_read_the_outcome_yet` (with the handler patched to return each member of `Outcome` in turn, `_process_frame` returns the same confirm: this task changes no ACK decision. The test is **deleted in T611**, which makes the outcome decide; it is named in T611's Files. The strict `xfail` of `test_unknown_device_frame_is_not_acked` must stay an expected failure after this task). Every test of this task that runs a real handler on a connection it builds itself takes the connection from `delegates_helper` or `conftest.mock_conn`, never a bare `AsyncMock()`: T613 opens a transaction on it.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\gateway\test_gateway_api.py -q`. Expected: FAIL with `ModuleNotFoundError: No module named 'backend.modules.gateway.domain.encode'`.
- [ ] **Step 3: Implement** `encode.py`, the return values, the keyword, `store_frame` and the two pass-throughs.
- [ ] **Step 4: Run.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_parser.py -q`. Expected: PASS, the T601 literals untouched, the three `xfail` tests still XFAIL, `test_reader_handlers.py` and `test_reader_delegates.py` unedited.
- [ ] **Step 5: Commit** `feat(gateway): T604 gateway.api stores a frame without the duplicate filter, and the handlers return an outcome`. PR body: the hardware note of T542 word for word, plus "the handlers gain a return value and `_handle_bee` one keyword with an unchanged default; `_process_frame`, decode, duplicate filter and ACK are untouched".

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_parser.py -q`
