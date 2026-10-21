# Future capabilities

**Version:** 0.1
**Status:** Draft (input to Phase E; nothing here is decided)
**Last updated:** 2026-10-04

Mutable catalogue of capabilities the system may gain later. Each entry names the business capability it
serves ([business-architecture.md](../business/business-architecture.md)), the principles it touches, and its
state. An entry becomes work only through Phase E (roadmap), after the field exercise, and through an ADR when it
adds a technology or an external connection.

**States:** *Idea* (recorded, not assessed) → *Assessed* (fit checked against principles and ADRs) →
*Candidate* (owner wants it; waits for roadmap slot) → *Planned* (in a plan under `docs/superpowers/plans/`).

---

## Catalogue

| ID | Capability | Serves | Principles touched | State | Detail |
|----|-----------|--------|--------------------|-------|--------|
| FC-01 | AI operator assistant: situation report, voice notes (no medical triage, owner 2026-10-04; no dispatch while ADR 3 holds) | 2. Alarm management, 5. Records and reporting | BP-01, BP-02, DP-01, DP-02, TP-01, TP-02 | Assessed | [fc-01-ai-assistant.md](fc-01-ai-assistant.md), hardware: [fc-01-ai-hardware.md](fc-01-ai-hardware.md) |
| FC-02 | Wind data and wind-shift warning | 3.3 Wind-shift warning | TP-02, BP-02 | Candidate (owner: first integration, 2026-10-03) | Draft spec `docs/superpowers/specs/2026-10-02-wind-shift-alerts-design.md` |
| FC-03 | APRS as a second position source | 1.1 Live position tracking | BP-01, TP-01 | Idea (owner: yes, 2026-10-03) | [application-architecture.md](../application/application-architecture.md), Section 6 |
| FC-04 | Meshtastic as a position and message source | 1.1, possibly two-way messages | BP-01, TP-01, ADR 3 | Idea (owner: yes, 2026-10-03) | Same |
| FC-05 | Packaged release: built frontend, service with auto-restart, pinned dependencies | 6.2 Install and start | TP-03, BP-01 | Idea | ADR 14 revisit conditions; R-11, R-25 |
| FC-07 | Generic field signal with category (obstacle, fire, other), own module | 5.2 Field reports | BP-01, DP-03 | Candidate (field exercise FX-04, after the vertical slices) | [field-exercise-findings.md](field-exercise-findings.md) |
| FC-06 | Operation entity: per-operation records, reports and retention | 5. Records and reporting | DP-03 | Idea | ADR 4 revisit conditions; BR-09, R-20 |

---

## How a future capability is assessed

1. **Inputs exist?** Check what the data sources really deliver (for example, RescuerBee frames carry position,
   battery and an SOS bit only: `docs/PROTOCOL.md`).
2. **Principles:** run the [How to check](../principles/architecture-principles.md#how-to-check-tests-for-reviews-and-agents)
   table. Personal data leaving the machine (DP-01) and anything that could hide or delay an alarm (BP-02) are
   blocking.
3. **ADRs:** list the decisions it builds on or would reopen.
4. **Field laptop:** CPU, RAM, disk and battery cost on a typical laptop.
5. **Smallest useful step:** what could be tried at an exercise without touching the alarm path.
