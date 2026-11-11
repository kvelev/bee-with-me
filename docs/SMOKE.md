# Smoke test before a PR into `develop`

A merge into `develop` builds the two images (`deploy/docker/backend.Dockerfile`, `frontend.Dockerfile`) and deploys
them to bee-dev for human testers. CI never builds or starts these images on a PR, so run this script yourself before
you open the PR. It takes about 2 minutes with a warm image cache.

## Run

Needs Python 3.11+ and Podman or Docker (the Podman machine must be running on Windows: `podman machine start`).

```powershell
.\tools\smoke.ps1                 # Windows
```
```bash
./tools/smoke.sh                  # Linux
```

The engine is `CONTAINER_ENGINE` (`podman` or `docker`), else Podman, else Docker. Options: `--engine podman|docker`,
`--no-build` (reuse the `smoke-local` images of the previous run).

Equivalent by hand: `python tools/smoke.py`. Nothing in `data/`, `tiles/` or `backend/uploads/` is used, no `.env` is
read or written. The database and the backend's upload/tile folders are named volumes created for the run.

## What it checks

It builds both images with the same Dockerfiles and context (repo root) as `deploy-develop.yml`, tagged `smoke-local`,
starts an empty PostGIS 16 and the backend with the environment of `deploy/k8s/app/backend.yaml`
(`ENABLE_TEST_ENDPOINTS=true`, read-only root, no capabilities), with random passwords generated for the run.

| Step | Check |
|---|---|
| engine ready | the engine answers (`podman machine start` is the usual fix) |
| build backend / frontend image | both Dockerfiles build |
| empty database up | PostGIS accepts TCP connections |
| a. migrations + backend start | the backend runs all migrations on the empty database and stays up |
| b. GET /health | 200 |
| c. admin login + token refresh | `POST /api/auth/login` as `admin` with the generated password, then `/api/auth/refresh` |
| d. live / users / devices | `GET /api/locations/live`, `/api/users/`, `/api/devices/` with the token: 200 |
| e. simulated frame reaches /ws | opens `/ws`, creates a user and device, `POST /api/test/simulate`, expects the `location_update` for that device |
| f. frontend image | nginx answers `GET /` with 200 and HTML containing `<div id="app">` (no browser) |
| g. GET /api/settings | with the token: 200 and a JSON object with `hq_radius_m` (the settings row exists; the route is served by the `settings` module, which the module list mounts behind the default auth, so this is the one step that exercises the loader and the module) |
| h. GET /api/fire/status | with the token: 200 and a JSON object with the key `feeds` (the route is served by the `fire` module behind the default auth) |
| i. GET /api/weather/current | with the token: 200, 502 or 503 (503 is the answer of an environment without `OWM_API_KEY`, which the smoke stack has; 502 = OpenWeatherMap unreachable). Any other status, 401 included, fails: it proves the `weather` module is mounted behind the login |
| j. GET /api/locations/sos | with the token: 200 and a JSON list of the open SOS alerts (the route is served by the `sos` module behind the default auth; an empty list is the normal answer of the fresh smoke database) |
| cleanup | containers, network and volumes are removed, also after a FAIL or Ctrl+C |

## Read the result

One line per step: `PASS`, `FAIL` (with the reason, and the last log lines of the backend when it did not start) or
`SKIP` (an earlier step it needs failed). The last line is `SMOKE PASSED` or `SMOKE FAILED`.
Exit code 0 = all PASS, 1 = at least one FAIL, 2 = no usable container engine. A `cleanup` FAIL names what is left
behind (`bee-smoke-*`): remove it with `podman rm -f` / `podman network rm` / `podman volume rm`.

Paste the PASS lines (or the failing line) into the PR description.

## Not checked

The browser UI, the map and tiles, the USB gateway and `hardware_reader`, PDF export, the fire/EFFIS feeds,
other roles than admin, a database that already has data, the Kubernetes manifests and ingress, and upgrades
between versions. A green `Deploy develop` does not replace this script and this script does not replace the CI.

Last verified run: 2026-11-07, commit 77b89fe on upstream/develop 98db703, Podman 6.1.4 (Windows, WSL machine): all 11 steps PASS, no bee-smoke-* left behind.
