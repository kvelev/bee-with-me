# 19. Module boundaries enforced by architecture tests with a ratchet

Date: 2026-10-05
Amended: 2026-11-07 (backend tool proposal and allowlist mechanics, from the step 0 plan)

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

## Decision

We will enforce the module rules of [ADR 17](0017-vertical-slice-modules.md) with **architecture tests** that run in
the normal suites: `backend/tests/architecture/` (pytest; module and layer import rules, owned-table writes, SQL only
in `infrastructure/`, manifest completeness, no cycles) and a frontend architecture test (vitest with
dependency-cruiser; modules import only other modules' `index.js`, pure `lib/`, platform imports no module).

**Tools (proposed, waiting for the owner's approval):** `import-linter` for the backend import rules (contracts in
a TOML file, allowlist as `ignore_imports`), plain pytest for SQL ownership and manifest completeness (allowlist in
`allowlist.json`), and `dependency-cruiser` driven from vitest on the frontend. Reasons: the ratchet is built into
import-linter (a stale ignore line fails the run), and the config is data, so an allowlist change is a one-line
diff.

The tests start with an **allowlist of today's violations** (a ratchet): new violations fail at once, a stale entry
fails (exact match), each migration step removes its own entries, and a test fails when the number of entries
grows compared with the merge base. At step 5 the allowlists are empty.

## Consequences

**Positive:**
- A violation is a red test while the change is made, not a review comment later.
- The rules are executable documentation for agents.

**Negative / Trade-offs:**
- A test dependency on each side: `import-linter>=2.16,<3` and `dependency-cruiser` at an exact version.
- The SQL ownership check is a text scan; unusual SQL may need an explicit allowlist entry.
- Allowlists live in three places (TOML, JSON, JSON); the "may not grow" tests guard all of them.

## Considered options

| Option | Summary | Pros | Cons |
|--------|---------|------|------|
| ✅ **Architecture tests with ratchet** | Rules as tests | Immediate, automatic | Test code to maintain |
| Convention plus review | Rules in standards | No tooling | Late, inconsistent |
| Imports checked automatically, SQL by review | Mixed | Less test code | Table ownership unguarded |

> ⚠️ **Requires stakeholder input (owner):** approve `import-linter` and `dependency-cruiser` as new dev
> dependencies. Alternative for the backend: pytest-archon (rules in test code); a stale exclude is accepted
> silently there, so "the list may only shrink" would need code we maintain.

## Related

- [modular-monolith.md](../application/modular-monolith.md) Sections 3.1, 8 and 9; ADR 17
- Step 0 plan: `docs/superpowers/plans/2026-11-07-vs-step0-kernel-and-guards.md` (tool measurement, T304 to T306)
