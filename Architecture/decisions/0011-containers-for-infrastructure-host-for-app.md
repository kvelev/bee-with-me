# 11. Containers for infrastructure, application on the host; Podman first

Date: 2026-10-03

## Status

Proposed (records the baseline 1.7.1)

**TOGAF Phase:** D (Technology Architecture)
**Decision Maker(s):** Project owner (kvelev)
**Stakeholders:** HQ operator, contributors
**Principles:** upholds TP-03, TP-01; trades off TP-03 partly (two runtimes on the host: Python and Node)

## Context

PostgreSQL with PostGIS is awkward to install natively on Windows and must be the same version everywhere.
The backend must open a USB HID (or serial) device, which is unreliable from inside a container on Windows
(Podman and Docker Desktop run containers in a VM). The maintainer uses Podman 6; others use Docker.

## Decision

We will run **infrastructure in containers** (PostgreSQL/PostGIS; the `tileserver-gl` container was removed on 2026-11-08) from one compose
file, and run the **backend and the map client on the host** (`.venv`, Node). Scripts choose the engine as
`CONTAINER_ENGINE` → `podman` → `docker`, never hard-code `docker`, and add a Podman-machine overlay on Windows
(host network, Postgres listening on 127.0.0.1). Documentation shows the Podman command first and the Docker
equivalent next to it. Database data lives in a bind mount (`data/pgdata`) or, on a Podman machine, a named
volume.

## Consequences

**Positive:**
- Same database version on every machine; no native PostGIS install.
- Direct USB access for the readers.
- Works with both engines.

**Negative / Trade-offs:**
- The host needs Python and Node. Node is pinned to a floor (22.12, 24 LTS recommended) by `engines` and
  `.nvmrc` in `frontend/` and checked by the start scripts; Python is not pinned.
- Two storage layouts (bind mount vs Podman named volume) to cover in backup and restore scripts.
- Podman on Windows needs `podman machine start` before the stack starts.

## Considered options

| Option | Summary | Pros | Cons |
|--------|---------|------|------|
| ✅ **Infrastructure in containers, app on host** | As built | USB works, DB reproducible | Host runtimes to install |
| Everything in containers | Backend with USB passthrough | One install step | USB passthrough unreliable on Windows VMs |
| Everything native | Install PostgreSQL/PostGIS on the host | No container engine | Version drift; hard on Windows |

## Related

- [technology-architecture.md](../technology/technology-architecture.md), ADR 2, ADR 12
