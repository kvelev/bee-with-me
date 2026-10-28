# Field exercise findings

**Version:** 0.1
**Status:** Draft (input to Phase E)
**Last updated:** 2026-10-21
**Source:** feedback from the first field test of the software, relayed by Kiril on 2026-10-21

Mutable document. Each finding gets an ID (`FX-nn`), a decision and its place in the order of work.

---

## 1. Findings

| ID | Finding | Cause (as known) | Decision | Path |
|----|---------|------------------|----------|------|
| FX-01 | **The app does not start without internet.** | The start scripts run `pip install -r requirements.txt` on every start (`start.ps1`, `start.sh`); offline, pip retries for minutes, then the script continues with an incomplete environment. Same for `npm install` when `node_modules` is missing. | Look locally first (installed packages, `vendor/wheels`, npm cache), try online only when something is missing, with a short timeout, then stop with a clear message naming what is missing. Skip the check when `requirements.txt` has not changed. Add a preparation script for home use and a one-click starter whose window stays open on error. | Bounded; design approved 2026-10-21; **Done** (B62, B64, B65): offline start verified on the dev machine 2026-10-21 with pip and npm pointed at a dead address; `prepare-offline` once with internet, then no download attempts. Field run pending |
| FX-02 | **The start is slow.** | Reported as caused by database migrations. Not measured. Candidates: `migrate status` subprocess with retries, `pg_dump` before pending migrations, container start. | Measure first: stopwatch timings per start phase, printed in debug output, in the scripts and the backend lifespan. Optimise only what the numbers show. | Measured 2026-10-21 (dev machine, B63 timings): backend `database pool 4.1 s`, `migrations 0.0 s`; `start.ps1` warm total 7.6 s (migration check 2.8 s). **Migrations are not the cause.** `localhost` resolves to `::1` first, the DB port is on `127.0.0.1` only, and a refused `::1` connect costs 2 s on Windows (×2 for the pool). Fixed in B67 (`127.0.0.1`). After: backend `database pool 0.0 s`, total 0.1 s (was 4.1 s). **Done** on the dev machine; field run pending. Also found: the map never recovered when the page loaded before the backend (B66, fixed) |
| FX-03 | **Visual bugs.** | Not yet listed. | Collect and review later. | Waits for the vertical slices |
| FX-04 | **Field report → generic field signal with a category**: obstacle, fire, other; no category selected by default (the operator must choose); colour by category. | Today a field report is a row in `fire_hotspots` (`source = 'field_report'`), part of the fire module. | New module (`field-reports`) with its own table; move to it. **No historical data is kept**: existing field reports are not migrated. | Architectural; after the vertical slices |

> ⚠️ **Requires stakeholder input (owner):** for FX-04, does a "fire" signal still show on the fire layer and count
> for anything in the fire alarm (today field reports never raise the alarm)?

---

## 2. Order of work (owner, 2026-10-21)

1. **Vertical slices first** ([ADR 17](../decisions/0017-vertical-slice-modules.md),
   [modular-monolith.md](../application/modular-monolith.md)). Small fixes wait for it.
2. **FX-04** as the first new module on the new structure.
3. FX-01, FX-02, FX-03 as decided above.

> ⚠️ **Requires stakeholder input (owner):** FX-01 stops the app from starting in the field. Does it also wait for
> the vertical slices, or is it the one exception done now? It touches only the start scripts.

---

## 3. Strategic question raised: internet-first or offline-first

The owner asked for a deeper, high-level look at what changes if the system moves from **offline-first** (today:
TP-01, TP-02) to **internet-first**, given that Starlink is standard in the field. This is to be brainstormed
separately.

Decisions that depend on the answer:

| Area | Offline-first today | Would be revisited |
|------|---------------------|--------------------|
| Principles | TP-01 no runtime internet; TP-02 online sources optional | Order and wording of TP-01 to TP-03; DP-01 (data stays on the machine) |
| Deployment | [ADR 2](../decisions/0002-single-field-machine-intranet-deployment.md) one field machine; [ADR 12](../decisions/0012-loopback-only-network-exposure.md) loopback only | Hosted or hybrid deployment, remote screens |
| Live channel | [ADR 15](../decisions/0015-live-channel-open-by-design.md) `/ws` open, safe only on loopback | Authentication of `/ws` and `/uploads`, TLS |
| Updates | [ADR 14](../decisions/0014-run-from-source-git-pull.md) git pull, dependencies on the laptop | Packaged releases, FX-01 |
| Maps and data feeds | Offline BG Mountains tiles; EFFIS, weather, wind as optional | Online basemaps as default (R-04) |
| Personal data | Local only, GDPR basis ADR 16 | Processor agreements, hosting location |
| AI assistant | Local model first ([FC-01](fc-01-ai-assistant.md)) | Cloud models |

> 📝 **Assumption:** until that brainstorm decides otherwise, offline-first and the current ADRs stay in force.
