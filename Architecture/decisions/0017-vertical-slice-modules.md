# 17. Modules as vertical slices across backend and frontend

Date: 2026-10-05

## Status

Proposed

**TOGAF Phase:** C (Application Architecture)
**Decision Maker(s):** Project owner (kvelev); proposed by Kiril
**Stakeholders:** Contributors, coding agents
**Principles:** upholds TP-03 (one process stays), BP-01 and BP-02 (fast path kept direct); refines ADR 6

## Context

The backend is organised by technical layer (`routers/`, `hardware_reader/`, shared files), with `fire/` already
close to a self-contained slice. Modules write into each other's tables (people deletion updates positions and
alerts; device deletion deletes positions and alerts), the hardware reader joins people and teams to build the live
payload, and `main.py` wires every task. On the frontend, `MapView.vue` and `useMap.js` (about 2300 lines) hold
every feature on the map. Parallel work by several agents collides in these files, and each future capability
(wind data, APRS, Meshtastic, AI report) would add to them.

## Decision

We will organise the code into **modules that are vertical slices**, with the same module names in
`backend/modules/` and `frontend/src/modules/`, around a shared `platform/` that knows no module. Each backend
module has a manifest (`module.py`), a public `api.py`, an HTTP router, a pure `domain/`, an `infrastructure/` for
SQL and external clients, and `tasks.py`. Each frontend module has a manifest (`index.js`) that contributes routes,
map layers, panels, banners, live handlers and i18n to the platform's map-shell. Only the owning module writes its
tables; other modules read them through declared read models. The module list and rules are in
[modular-monolith.md](../application/modular-monolith.md).

Positions, SOS and fire alerts keep a direct path (gateway → tracking/sos in one transaction → `pg_notify` → `/ws`)
that never waits for any queue.

## Consequences

**Positive:**
- An agent working on one module touches only that module's folders.
- A new module is a new folder plus one line in the module list.
- The live payload becomes thin (IDs and position data), which also removes phones and photo paths from `/ws` (R-22).

**Negative / Trade-offs:**
- A large, step-by-step restructuring; every file moves once.
- More files and an extra indirection (`api.py`) for small modules.
- Step 3 of the migration touches the hardware path and needs real-hardware validation.

## Considered options

| Option | Summary | Pros | Cons |
|--------|---------|------|------|
| ✅ **Vertical slices, backend and frontend** | Same modules on both sides | Parallel work, easy new modules | Large migration |
| Backend only | Frontend unchanged | Smaller | MapView stays the conflict point |
| Folders only, no rules | Move files, keep free SQL | Fast | Hidden coupling remains |

## Related

- ADR 6, ADR 7, ADR 18, ADR 19; [modular-monolith.md](../application/modular-monolith.md)
