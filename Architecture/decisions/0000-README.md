# Architecture decision records

Index of all ADRs for Bee With Me. Format and rules: [ADR 1](0001-record-architecture-decisions.md).

- File names: `NNNN-short-title.md` (four digits, kebab-case); numbers are never reused.
- Layout: adr-tools (`# N. Title`, `Date:`, `## Status`, `## Context`, `## Decision`, `## Consequences`),
  so the folder can be imported by Structurizr.
- Status: `Proposed` (open pull request) → `Accepted` (merged by the owner) → `Deprecated` | `Superseded by N`.
- Every ADR cites the principle IDs it upholds or trades off: [architecture principles](../principles/architecture-principles.md).

| ADR | Title | Status | Date | Phase |
|-----|-------|--------|------|-------|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | Proposed | 2026-10-03 | Preliminary |
| [0002](0002-single-field-machine-intranet-deployment.md) | Single field machine, intranet-only deployment | Proposed | 2026-10-03 | A |
| [0003](0003-alarm-response-outside-the-system.md) | Alarm response stays outside the system | Proposed | 2026-10-03 | B |
| [0004](0004-no-operation-entity.md) | No "operation" entity for now | Proposed | 2026-10-03 | B |
| [0005](0005-postgresql-postgis-raw-sql.md) | PostgreSQL with PostGIS, accessed with raw SQL | Proposed | 2026-10-03 | C |
| [0006](0006-modular-monolith-in-process-tasks.md) | Modular monolith with in-process background tasks | Proposed | 2026-10-03 | C |
| [0007](0007-pg-notify-websocket-live-channel.md) | Live updates through pg_notify and one WebSocket | Proposed | 2026-10-03 | C |
| [0008](0008-local-accounts-jwt.md) | Local accounts with JWT and three roles | Proposed | 2026-10-03 | C |
| [0009](0009-vue-spa-openlayers.md) | Vue 3 single-page app with OpenLayers | Proposed | 2026-10-03 | C |
| [0010](0010-numbered-sql-migrations.md) | Numbered SQL migrations applied at start-up after a backup | Proposed | 2026-10-03 | C |
| [0011](0011-containers-for-infrastructure-host-for-app.md) | Containers for infrastructure, application on the host; Podman first | Proposed | 2026-10-03 | D |
| [0012](0012-loopback-only-network-exposure.md) | Every listener on loopback; screens are attached to the field laptop | Proposed | 2026-10-03 | D |
| [0013](0013-secrets-and-settings-in-env.md) | Secrets and settings in a local .env file | Proposed | 2026-10-03 | D |
| [0014](0014-run-from-source-git-pull.md) | Run from source, update with git pull, no packaged release or CI for now | Proposed | 2026-10-03 | D |
| [0015](0015-live-channel-open-by-design.md) | The live channel /ws is open by design | Proposed | 2026-10-04 | C, D |
| [0016](0016-lawful-basis-asp-contract.md) | Lawful basis for personal data: the volunteer contract with ASP | Proposed | 2026-10-04 | B, C |
| [0017](0017-vertical-slice-modules.md) | Modules as vertical slices across backend and frontend | Proposed | 2026-10-05 | C |
| [0018](0018-transactional-outbox.md) | Transactional outbox with idempotent handlers for cascades between modules | Proposed | 2026-10-05 | C |
| [0019](0019-architecture-tests.md) | Module boundaries enforced by architecture tests with a ratchet | Proposed | 2026-10-05 | D, G |

## Writing a new ADR (people and agents)

1. Take the next free number; copy the layout of an existing ADR.
2. Fill Context (forces, constraints), Decision ("We will X because Y"), Consequences (positive, negative,
   risks), Considered Options (at least two real alternatives).
3. Cite principle IDs, for example `Upholds: TP-01, DP-02. Trades off: BP-02 (reason)`.
4. Add a row to the table above in the same pull request.
5. To replace a decision, write a new ADR and set the old one's status to `Superseded by N`. Do not rewrite
   an accepted ADR.
