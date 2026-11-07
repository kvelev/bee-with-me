# 12. Every listener on loopback; screens are attached to the field laptop

Date: 2026-10-03

## Status

Proposed

**TOGAF Phase:** D (Technology Architecture)
**Decision Maker(s):** Project owner (kvelev)
**Stakeholders:** HQ operator, command post team, partner organisations
**Principles:** upholds DP-01, DP-02; trades off flexibility (no second client machine)

## Context

The owner confirmed (2026-10-03) that the wall display is a monitor attached to the field laptop and that
Starlink internet is standard at every operation. The laptop is therefore always on a network shared with
whoever else uses the Starlink router. Today the database, the backend, the Vite dev server and the Node tile server
all listen on loopback by default. The live channel (`/ws`) is open by design
([ADR 15](0015-live-channel-open-by-design.md)); photos (`/uploads`) and CORS are not protected (R-03, R-09).
Loopback binding is what keeps all of them off the network.

## Decision

We will keep **every listener bound to loopback** (`127.0.0.1` / `localhost`): PostgreSQL, the backend, the map
client's server and the tile server. All screens, including the wall display, are attached to the field laptop.
Binding any listener to another interface is a deliberate change that requires, first: a new decision on the
open live channel (revisiting ADR 15), authenticated photos, restricted CORS, a changed default password, and
a new ADR.

## Consequences

**Positive:**
- Nothing is reachable from the Starlink network or any LAN, whatever the firewall says.
- The open live channel and photo folder are acceptable risks while this holds.

**Negative / Trade-offs:**
- No tablets, second laptops or partner screens over the network.
- A contributor who adds `--host 0.0.0.0` (or Vite `server.host`) silently exposes personal data; reviews must
  check this (TP and DP checks).

## Considered options

| Option | Summary | Pros | Cons |
|--------|---------|------|------|
| ✅ **Loopback only, attached screens** | As built and as used | Safe with open endpoints | One machine for all screens |
| LAN exposure with a firewall | Bind to the LAN interface, block Starlink side | More screens | Firewall rules differ per OS and network; open endpoints exposed to the LAN |
| LAN exposure after hardening | Revisit `/ws` (ADR 15), authenticate photos, TLS | Proper multi-user | Work not done yet; needs a new ADR |

## Risks

| Risk ID | Description | Impact | Mitigation |
|---------|-------------|--------|------------|
| R-02, R-22 | Open live channel (by design, ADR 15) | H | Acceptable only while loopback holds |
| — | Someone changes a binding | H | Review check; start scripts could warn on non-loopback bindings |

## Related

- [technology-architecture.md](../technology/technology-architecture.md) Section 3, ADR 2, ADR 8
