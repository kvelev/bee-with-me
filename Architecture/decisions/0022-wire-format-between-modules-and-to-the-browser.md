# 22. Wire format between modules and to the browser: no protobuf for now

Date: 2026-11-11

## Status

Proposed

Relates to [ADR 6](0006-modular-monolith-in-process-tasks.md) (one process), [ADR 7](0007-pg-notify-websocket-live-channel.md)
(`pg_notify` and one WebSocket), [ADR 15](0015-live-channel-open-by-design.md) (open live channel),
[ADR 17](0017-vertical-slice-modules.md) (modules as vertical slices) and [ADR 19](0019-architecture-tests.md)
(architecture tests).

**TOGAF Phase:** C (Application Architecture)
**Decision Maker(s):** Project owner (kvelev); proposed by Kiril, who asked whether services should talk protobuf
instead of REST/JSON
**Stakeholders:** Contributors, the RescuerBee hardware owner (Kiril Penev), HQ operator
**Principles:** upholds TP-01 (offline, nothing to fetch), TP-03 (one machine, reproducible start), BP-03 (failures
visible), DP-02 (payloads carry only what is needed); trades off a machine-checked schema shared by backend and
frontend (see option 4)

## Context

The question was whether a binary schema format (protobuf) would be better than REST and JSON between the
"services". What the code and documents show today:

- **There are no services to connect.** The backend is one process ([ADR 6](0006-modular-monolith-in-process-tasks.md)).
  Modules call each other as Python functions through `modules/<name>/api.py`
  ([ADR 17](0017-vertical-slice-modules.md)); there is no network and no serialisation between them. The gateway
  is a task of the same process: `main.py` starts the HID reader with `asyncio.create_task`. Nothing in
  `requirements*.txt` or `frontend/package.json` is a serialisation or RPC library.
- **Browser and backend** use REST with JSON (FastAPI also publishes the OpenAPI page at `/docs`) and one WebSocket
  `/ws` with JSON messages. The writer calls `pg_notify(channel, json)`; `core/ws.py` parses the text and forwards
  `{**data, 'type': channel}` to every client. A `pg_notify` payload is **text** and limited to 8000 bytes, so a
  binary body would first have to be encoded as text (for example base64) on the way through PostgreSQL.
- **Message size.** `location_update` has 20 keys (`tracking/domain/payload.py`). A sample message with realistic
  values, built by hand and serialised with `json.dumps` (not a benchmark of the running system), is about 650 bytes
  with the personal fields and about 450 bytes without them (the key set of T547, see
  [the tracking plan](../../docs/superpowers/plans/2026-11-10-vs-step2-tracking-sos.md), section 1.4).
- **Volume is not known.** [Architecture.md](../Architecture.md) records the RescuerBee frame interval as an open
  assumption until the hardware owner confirms it; this ADR therefore states no messages-per-minute figure. The
  deployment is one field machine, one gateway, one operator
  ([ADR 2](0002-single-field-machine-intranet-deployment.md)), every listener on loopback
  ([ADR 12](0012-loopback-only-network-exposure.md)).
- **Device to gateway is already compact, but it is text.** `docs/PROTOCOL.md` describes ASCII frames
  `##<comma separated fields>@<decimal CRC-16>\r\n` (Cmd=30 has 25 fields), carried in 64-byte HID packets. It is
  agreed with the hardware owner and pinned by `test_parser.py`. It is a boundary of this ADR, not a subject.
- **The contract of the live messages is explicit since T547** (commit `c401b14`, PR for branch `feature/vs-2-t547`):
  `tracking/domain/payload.py` holds the frozen dataclasses `PositionFix` (15 keys) and `PersonalDetails` (5 keys);
  `sos/domain/payload.py` holds `SosAlert` (5 keys) and `SosPerson` (`full_name`, `rank`). The setting
  `live_personal_fields` in `core/config.py` (environment variable `LIVE_PERSONAL_FIELDS`, default `true`) decides
  whether the personal part is added: on gives the 20-key message the browsers always got, off gives the thin one.
  `test_reader_handlers.py` compares the message keys with fixed sets (`LOCATION_KEYS`, `SOS_KEYS`).
- **Not everything is under the switch.** The `fire_alert*` messages (`fire/domain/models.py`) still carry
  `full_name` and `rank`, and the switch does not reach them.

## Decision

We will **not introduce protobuf now**. Instead:

1. **Inside the process** modules keep calling each other through `api.py` functions. No wire format exists there
   and none is added.
2. **To the browser** REST and `/ws` stay JSON.
3. **The contract of the live messages is held by typed models and tests, as T547 built them**: the frozen
   dataclasses named in Context in each module's `domain/` (pure, no I/O, [ADR 17](0017-vertical-slice-modules.md)),
   and tests that compare the serialised message with the exact key set. Adding, removing or renaming a key fails a
   test and is visible in review. This ADR adds nothing to the code; it records that this, not protobuf, is the
   contract. `docs/PROTOCOL.md` is not touched.
4. The decision is reviewed when one of the **triggers** below becomes true.

## Considered options

| Option | What we gain | What we pay | For this project |
|--------|--------------|-------------|------------------|
| 1. ✅ **No change** (functions inside, JSON outside) plus typed models and key tests | Nothing new to install or learn; the Network tab shows readable messages; REST stays self-documenting through `/docs`; offline install unchanged (TP-01, TP-03) | The schema is not shared with the frontend by a generator; a key rename still needs a manual change in `frontend/src` | Fits one process, one operator, loopback |
| 2. Protobuf over `/ws` to the browser | Smaller messages; one `.proto` file as the contract | `.proto` files and a code generator for Python **and** Vue; a build step in both `update` scripts and CI ([ADR 20](0020-offline-start-separate-update.md): start installs nothing, so the generator and its packages must be installed in advance); `pg_notify` carries text only, so base64 or a re-encoding step in `core/ws.py`; messages unreadable in the browser's Network tab without a decoder; REST would stay JSON, so two formats | About 450 bytes per message gains little on a loopback socket; the cost is paid by one maintainer |
| 3. Protobuf/gRPC between separate processes | A typed contract and streaming between services | Needs services to exist: gRPC adds a server, ports and generated stubs to a single field laptop; browsers cannot call gRPC directly (a proxy is needed); more listeners to bind to loopback ([ADR 12](0012-loopback-only-network-exposure.md)) | Premature: there is no second process (see triggers) |
| 4. JSON with a schema (pydantic models, OpenAPI or JSON Schema, generated TypeScript types or a checked JSON file) | One machine-readable contract for REST and `/ws`; the frontend can be checked against it; text stays readable | A generation or check step in CI; pydantic models must be kept in sync with the dict builders; the frontend is plain JavaScript (no TypeScript types to receive), so the gain is a checked schema file, not compiler errors | The natural next step, but only if option 1's key tests stop being enough; not needed now |

## Consequences

**Positive:**
- No new dependency, build step or runtime on the field machine; the update script and CI stay as they are.
- Messages stay readable in the browser and in `psql` (`LISTEN`), which helps a single operator debug in the field.
- The contract of the two most important messages (`location_update`, `sos_alert`; BP-01, BP-02) is explicit in
  typed models and tests (T547).

**Negative / Trade-offs:**
- No generated, shared schema between backend and frontend; a mismatch is found by tests and review, not by a compiler.
- JSON is larger than protobuf; at the size above this does not matter on loopback.
- The typed models are an extra file per message to keep in step with the code that builds the message.
- `fire_alert`, `fire_alert_updated` and `fire_alert_repeat` are not covered by `LIVE_PERSONAL_FIELDS`: `fire_alert*` still
  carry `full_name` and `rank` (`fire/domain/models.py`). Their keys are not yet held by typed models either.
- The code says `PersonalDetails` and the switch are to be removed together in a T547 follow-up. If that happens, the
  models for the personal part go with them; `PositionFix` and `SosAlert` stay.

**Reconsider this ADR when any of these becomes true** (each can be checked in the repository):
1. **The gateway runs as its own process**: `main.py` no longer starts the HID reader as a task, or another process
   writes to `location_events` or calls `pg_notify`.
2. **A second client outside the browser appears** (a mobile app, another server, a bridge such as APRS or
   Meshtastic that is not a Python function in this process): a route or a socket that something other than
   `frontend/` calls.
3. **Live traffic grows by an order of magnitude**: once the hardware owner confirms the frame interval, a
   measured rate of `location_update` messages per second at the gateway, or `pg_notify` payloads approaching the
   8000-byte limit, more than about ten times the rate observed in the first real operation.
4. **A contract shared with the firmware is needed**: any change that makes the device frame format and a backend
   message come from one schema (this would also need Kiril Penev's agreement).

If trigger 1 or 2 fires, option 3 (or a JSON-schema option 4 first) is evaluated in a new ADR that supersedes this one.

**What we do instead of protobuf:** keep the T547 models and key tests as the contract; extend the same
approach to the `fire_alert*` messages when their personal keys are decided (the owner's call, not this ADR's); revisit
option 4 (a schema generated from the models) if a key mismatch between backend and frontend reaches bee-dev even once.

## Related

- [api-contracts.md](../application/api-contracts.md) Section 3 (WebSocket messages), `docs/PROTOCOL.md` (device frames),
  [modular-monolith.md](../application/modular-monolith.md)
- Code: `backend/core/ws.py`, `backend/modules/tracking/domain/payload.py`, `backend/modules/tracking/api.py`
