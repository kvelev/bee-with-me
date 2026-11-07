# 21. Node tile server for offline MBTiles maps

Date: 2026-11-07

## Status

Proposed

Relates to [ADR 11](0011-containers-for-infrastructure-host-for-app.md) (containers for infrastructure),
[ADR 12](0012-loopback-only-network-exposure.md) (loopback), [ADR 13](0013-secrets-and-settings-in-env.md)
(settings in `.env`) and [ADR 20](0020-offline-start-separate-update.md) (start installs nothing).

**TOGAF Phase:** D (Technology Architecture)
**Decision Maker(s):** Project owner (kvelev); the component was contributed by Kiril Penev (PR #53), this ADR
records it
**Stakeholders:** HQ operator, contributors
**Principles:** upholds TP-01 (offline maps); trades off TP-03 (reproducible start: unpinned manual install), DP-02
(open CORS) and ADR 11 (a host process, not a container)

## Context

Pull request #53 added `tile-server/` to the repository: a small Node.js HTTP server (`server.js`, packages
`better-sqlite3` and `dotenv`). Nothing in the architecture documents described it, and the older tile service in
`docker/docker-compose.yaml` (`tileserver-gl`, reading `tiles/`) was already broken (R-12).

What the code does:

- Reads `.mbtiles` files from `tile-server/maps/` (git-ignored, so the map data is not in the repository) and serves
  `GET /tiles/{z}/{x}/{y}.jpg?map=<name>`, `GET /api/maps`, `GET /api/current` and `GET /api/select/<file>.mbtiles`.
  The last one changes the map the server serves, for every client.
- Takes its host and port from `VITE_TILE_HOST` and `VITE_TILE_PORT` in the project `.env`
  (`.env.example`: `127.0.0.1:8081`). The map client builds tile URLs from the same variables
  (`frontend/src/composables/useMap.js`) and offers the choice in `SelectOfflineMap.vue`.
- Is started by `start.ps1` and `start.sh` on the host, in its own window or process, next to the backend and Vite.
- Sends `Access-Control-Allow-Origin: *` and has no authentication.
- Has no `package.json` or lock file in the repository (both are git-ignored); the README says to run
  `npm install better-sqlite3 dotenv` by hand. The start scripts only warn when the packages are missing.

## Decision

We will keep the Node tile server as the way to show **offline MBTiles maps** (TP-01), run on the host as
a fourth local process, and treat the points below as conditions of this ADR, not as accepted facts:

1. It binds to loopback only (ADR 12). The server must refuse to start when `VITE_TILE_HOST` is missing or is not
   a loopback address; Node's default (all interfaces) is not acceptable.
2. Its dependencies are pinned and installed by the update script, not by hand (ADR 20): `package.json` and the
   lock file are committed, the update script installs them, and start only checks.
3. `Access-Control-Allow-Origin` is limited to the map client's origin, and `/api/select` stops changing server
   state from a plain `GET` (R-03, DP-02).
4. The default port does not collide with another listener (the start scripts' fallback `8080` is the port of
   `tileserver-gl` in the compose file).

The decision whether this server **replaces** `tileserver-gl` (compose service `tiles`, R-12) or **complements**
it stays **open** for the owner.

> ⚠️ **Requires stakeholder input (owner):** does the Node tile server replace `tileserver-gl` or complement it?
> If it replaces it, the compose service and R-12 are removed in a separate change (`docker/` is owner-approved
> territory).

> ⚠️ **Requires technical clarification (Kiril Penev):** why the server lives in Node instead of the existing
> backend (`/tiles` is already proxied to it) or the container, and how `.mbtiles` files reach `tile-server/maps/`.

## Consequences

**Positive:**
- Offline maps work without a container engine and without the internet (TP-01); the operator picks the map in the UI.
- Map files stay outside git (`tile-server/maps/.gitignore`), which suits large binary files.

**Negative / Trade-offs:**
- A second runtime (Node, plus a native module, `better-sqlite3`) on the field machine; its install needs the
  internet once (R-25 applies).
- Until conditions 1 to 4 are met: unpinned dependencies, open CORS, an unauthenticated state-changing `GET`, and
  a listener whose bind address depends on `.env` (R-27).
- ADR 11 said infrastructure runs in containers; this server runs on the host. ADR 11 stays valid for the database.
- Two tile services exist in the repository until the open question above is answered.

## Considered options

| Option | Summary | Pros | Cons |
|--------|---------|------|------|
| ✅ **Node MBTiles server on the host** (as contributed) | Small server, `.mbtiles` in a folder | Works today, no container, simple map switch | Unpinned install, extra runtime, needs the conditions above |
| Fix `tileserver-gl` in the container | Pin the image, repair the command | One tile service, container model of ADR 11 | Heavier; the Podman machine on Windows adds a moving part; still needs `tiles/` prepared |
| Serve `.mbtiles` from the FastAPI backend | One process fewer | No Node, one auth and CORS model | New backend code on the hardware host; the contributed server would be dropped |

## Related

- [technology-architecture.md](../technology/technology-architecture.md) Sections 1 to 3; risks R-12 and R-27
  in [risk-register.md](../governance/risk-register.md)
- `tile-server/README.md`, `tile-server/server.js`, `frontend/src/views/SelectOfflineMap.vue`
