# 18. Transactional outbox with idempotent handlers for cascades between modules

Date: 2026-10-05

## Status

Proposed

**TOGAF Phase:** C (Application Architecture, Data Architecture)
**Decision Maker(s):** Project owner (kvelev); proposed by Kiril
**Stakeholders:** Contributors, HQ operator (deletions), data subjects
**Principles:** upholds BP-03 (failures visible), DP-03 (deletion completes), DP-02 (events carry IDs only);
trades off a short delay for cascades

## Context

With modules owning their tables ([ADR 17](0017-vertical-slice-modules.md)), a change in one module that others
must react to (a person deleted, a device deleted, settings changed) can no longer be a direct SQL write into their
tables. The reaction must not be lost if a module fails, GWIS must not run twice, and a deletion of personal data must
not stop half-way.

## Decision

We will use a **transactional outbox**: the owning module writes its change and an event row in the same
transaction; a platform dispatcher, woken by `pg_notify` after commit and polling as a fallback, delivers each event
to the subscribed handlers. Each handler records `(event_id, handler)` in an inbox table in the same transaction as
its work, so repeated delivery is harmless. Failed deliveries retry with backoff and then go to a dead-letter table
with a visible warning and manual retry.

**Deletion of personal data** uses soft delete first; the hard delete runs only after every subscriber has
confirmed. Event payloads carry IDs only; outbox and inbox rows have a short retention.

The outbox is **not** used for positions, SOS or fire alerts; those use the direct path of ADR 17.

## Consequences

**Positive:**
- Cascades survive crashes and restarts; nothing is half-done silently.
- New modules subscribe to existing events without changing the publisher.

**Negative / Trade-offs:**
- Three new tables, a dispatcher task and a soft-delete marker on `users`.
- Cascades are eventually consistent (normally well under a second).
- Handlers must be written to be idempotent.

## Considered options

| Option | Summary | Pros | Cons |
|--------|---------|------|------|
| ✅ **Transactional outbox + inbox** | Event in the same transaction, idempotent handlers | Reliable, extensible | More moving parts |
| Synchronous in-process events in one transaction | Subscribers run inside the publisher's transaction | Simple, strongly consistent | One failing subscriber blocks the publisher |
| Direct calls to other modules | Publisher calls each consumer | Explicit | Publisher must know every consumer |

## Related

- [modular-monolith.md](../application/modular-monolith.md) Section 5; ADR 7, ADR 17
