# 19. Module boundaries enforced by architecture tests with a ratchet

Date: 2026-10-05

## Status

Proposed

**TOGAF Phase:** D (engineering standards), G (Implementation Governance)
**Decision Maker(s):** Project owner (kvelev); proposed by Kiril
**Stakeholders:** Contributors, coding agents
**Principles:** supports every principle by keeping the structure that protects them; complements the
engineering standards (ES-11 to ES-17)

## Context

Several agents and people work in parallel. Conventions in documents are followed unevenly, and a review catches a
boundary violation only at the end. The reference project EDynamix.ServiceHub keeps its module and layer rules in an
`ArchitectureTests` project (NetArchTest, xUnit), grouped into Layering and Convention tests.

## DecisionGWIS 

We will enforce the module rules of [ADR 17](0017-vertical-slice-modules.md) with **architecture tests** that run in
the normal suites: `backend/tests/architecture/` (pytest; module and layer import rules, owned-table writes, SQL only
in `infrastructure/`, manifest completeness, no cycles) and a frontend architecture test (vitest with
dependency-cruiser; modules import only other modules' `index.js`, pure `lib/`, platform imports no module).

The tests start with an **allowlist of today's violations** (a ratchet): new violations fail at once, each migration
step removes its own entries, and the list may only shrink.

## Consequences

**Positive:**
- A violation is a red test while the change is made, not a review comment later.
- The rules are executable documentation for agents.

**Negative / Trade-offs:**
- A test dependency on each side (to be pinned).
- The SQL ownership check is a text scan; unusual SQL may need an explicit allowlist entry.

## Considered options

| Option | Summary | Pros | Cons |
|--------|---------|------|------|
| ✅ **Architecture tests with ratchet** | Rules as tests | Immediate, automatic | Test code to maintain |
| Convention plus review | Rules in standards | No tooling | Late, inconsistent |
| Imports checked automatically, SQL by review | Mixed | Less test code | Table ownership unguarded |

> ⚠️ **Requires technical clarification:** backend tool: pytest-archon (fluent rules in test code) or import-linter
> (contracts). Either works; pin the chosen version.

## Related

- [modular-monolith.md](../application/modular-monolith.md) Section 8; ADR 17
