# Vertical slices, step 2: the `weather` module (backend proxy and frontend panel) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `weather` a module on both sides: the OpenWeatherMap proxy becomes `backend/modules/weather/`, and the weather buttons, the info panel, the legend and the wind animation leave `MapView.vue` for `frontend/src/modules/weather/`, with no change the operator can notice.

**Architecture:** The backend is one file with no table: `backend/routers/weather.py` moves unchanged to `backend/modules/weather/http.py` and the old path becomes a `sys.modules` alias, so `test_api_weather.py` (which patches `weather.httpx`, `weather.settings` and `weather._tile_cache`) runs unedited. The frontend moves the two pure libraries first and the map UI second; the UI is contributed through the panel hosts that the fire plan adds (T504). The weather tile layer itself (`setWeatherLayer`, the authenticated tile loader, z-index 2) stays inside the `useMap` facade until step 5.

**Tech Stack:** Python 3.11+, FastAPI, httpx, import-linter, pytest; Vue 3, Pinia, OpenLayers 10, vitest. No new dependency.

**Spec:** [`docs/superpowers/specs/2026-10-31-vertical-slices-programme-design.md`](../specs/2026-10-31-vertical-slices-programme-design.md) sections 5 ("Step 5": a backend `weather` module exists with 10 tests), 6, 7; `Architecture/application/modular-monolith.md` sections 3, 4, 7, 9; ADR 17, 19; `Architecture/principles/architecture-principles.md` (TP-01, TP-02, DP-01). Template: [`2026-11-10-vs-step1-settings.md`](2026-11-10-vs-step1-settings.md) section 1. Contribution contract: [`2026-11-10-vs-map-shell.md`](2026-11-10-vs-map-shell.md) section 1 and [`2026-11-10-vs-step2-fire.md`](2026-11-10-vs-step2-fire.md) section 1.2.

**Base:** `upstream/develop` at `7f874bc`. Execution branches: `feature/vs-2-<task>` off `develop`, one PR per task. Wave overview: [`2026-11-10-vs-wave2-overview.md`](2026-11-10-vs-wave2-overview.md).

## Global Constraints

- The decisions and rules of the fire plan's Global Constraints apply unchanged (base branch, kernel names, frozen files, aliases until step 5, no behaviour change, auth by default, existing tests unedited except import and mock paths, allowlist lines only with approval, tags `T52x`, `frontend-designer` for `.vue` and `.css`, entry chunk base 167,61 kB stated before and after in every frontend PR).
- **The weather layer stays in the facade.** `setWeatherLayer`, `loadWeatherTile` and `loadRecolored` of `useMap.js` (lines 407 to 460) and the z-index `Z.weather` are not moved or edited in this wave; the weather panel calls `setWeatherLayer` through the map context. Step 5 decides whether the layer becomes a map entry.
- The API key never reaches the browser and never reaches a log: the `_RedactAppid` filter on the `httpx` logger and the `OWM_API_KEY` / `VITE_OWM_API_KEY` fallback of `core/config.py` are untouched (DP-02).
- Weather is optional and may be down: without a key every route answers 503, an unreachable upstream answers 502, and neither may slow the map or the alarms (TP-02). No task adds a call, a retry or a timer.
- `frontend/src/api/index.js` (`getWeatherCurrent`, `getWeatherBox`, `getWeatherTile`) is not edited: the API client is the platform's and a security-critical path.

## Review Focus

1. The proxy must stay behind a login after the move: the loader adds the auth dependency, the routes keep their own, and none is listed as public (T520, `test_every_weather_route_needs_a_login`).
2. The key must not appear in the log under the new logger name either: the filter is installed when the module is imported, and the module is imported when the module list is read (T520, `test_the_appid_filter_is_installed_by_importing_the_module_list`).
3. Leaving the map with the wind layer on must stop the animation frame and the `moveend` listener; today `onUnmounted` of `MapView.vue` does it, afterwards the panel must (T522, `unmount stops the animation and removes the map listener`).
4. A panel is mounted before the map exists (children mount before the parent's `onMounted`): the panel must wait for `context.hostMap`, not read the map once (T522, `the panel attaches to a map that appears after mount`).
5. `box/city` refused by the OWM plan (`{"denied": true}`) must still switch the wind source to Open-Meteo and stop asking for the session (T522, `a denied box request falls back and is not repeated`).

---

## 1. What moves where

| Today | After | Old path | Task |
|-------|-------|----------|------|
| `backend/routers/weather.py` (127 lines, 3 routes, no SQL) | `backend/modules/weather/http.py`, unchanged | alias `backend/routers/weather.py` | T520 |
| `frontend/src/lib/weatherTiles.js`, `lib/wind.js` and their tests | `frontend/src/modules/weather/lib/` | re-exports until step 5 | T521 |
| the weather texts of the `map` namespace (`map.weather.*`, `map.weatherFeels`, `map.weatherWind`, `map.weatherFrom`, `map.weatherGusts`, `map.weatherHumidity`, `map.weatherClouds`, `map.weatherWindSource` and the wind-source labels) | `frontend/src/modules/weather/i18n/{en,bg}.js`, same dotted keys | none | T521 |
| `MapView.vue`: `WEATHER_LAYERS` (lines 343 to 367), the button row (template 92 to 99), the wind canvas, the info panel and the legend (template 276 to 310), `weatherLayerId`, `weatherInfo`, `weatherTimer`, `toggleWeather`, `scheduleWeatherFetch`, `fetchWeather`, `windDirLabel`, the wind animation (lines 935 to 1198), the `moveend` wiring | `frontend/src/modules/weather/{layers.js, ui.js, components/WeatherToolbar.vue, components/WeatherPanel.vue}` | none | T522 |

The backend file is not split into `infrastructure/` and `http.py`: it runs no SQL, the tests patch names on the one module, and a split would change what `weather.httpx` and `weather._tile_cache` point at. modular-monolith.md 3.1 puts external clients in `infrastructure/`; that split is left to step 5 and listed in section 6.

**Timers.** `weatherTimer` (the debounce of the weather fetch after `moveend`) and the wind animation frame (`windAnimFrame`) are weather's and move in T522. Nothing else in this plan owns a timer.

## 2. File map and who else touches each file (as of `7f874bc`)

Commands used: `git grep -nE "routers(\.| import |/)weather|weather_router" -- backend tools`; `git grep -noE "\bweather\.[A-Za-z_]+" -- backend/tests`; `git grep -nE "from '[^']*(lib/weatherTiles|lib/wind)" -- frontend/src`; `git grep -nE "vi\.mock\('[^']*(weatherTiles|wind)" -- frontend/src` (prints nothing); `git grep -nE "weather|wind" -- frontend/src/views/MapView*.test.js`.

| File | This plan | Also read or written by |
|------|-----------|-------------------------|
| `backend/routers/weather.py` | T520: becomes the alias | `backend/tests/conftest.py:20,34`, `backend/tests/test_api_weather.py:8,38-40,102` |
| `backend/main.py` (hot) | T520: `weather` leaves the import line 19 and line 279 | fire T502, T503; tracking T540 |
| `backend/modules/registry.py` (hot) | T520 adds one line | fire T502; tracking T540 |
| `backend/tests/architecture/importlinter.toml`, `approved_additions.py` (hot) | T520: 1 line deleted, 1 contract and 1 alias line added; `backend.modules.weather` added to the `source_modules` of every other boundary contract | fire T502, T503; tracking T540 |
| `tools/smoke.py`, `backend/tests/test_smoke_script.py`, `docs/SMOKE.md` | T520 adds step i | fire T502 (step h), tracking T540 (step j) |
| `frontend/src/modules/index.js`, `frontend/src/i18n/en.js`, `bg.js` (hot) | T521 | fire T505, tracking T544 |
| `frontend/src/lib/weatherTiles.js`, `lib/wind.js` | T521 moves them and leaves re-exports (kept until step 5) | `views/MapView.vue:329-330` until T522 |
| `frontend/src/views/MapView.vue` (hot) | T522 | fire T504, T506 to T508; overview T580; tracking T545, T548 |
| `frontend/src/composables/useMap.js` | not edited | the weather functions stay in it |

No conflict is expected with the other two plans beyond the hot files above; their order is in the overview.

## 3. Task order, PRs, reviewers, parallel work

| PR | Task | Content | Needs | Owner | Reviewers |
|----|------|---------|-------|-------|-----------|
| 1 | T520 | backend `weather` module | fire T500 (the loader guard is merged first) | implementer | breaker + security-reviewer (`routers/**`, `main.py`) |
| 2 | T521 | frontend libraries, texts and the manifest | nothing (assembly chain) | implementer | breaker |
| 3 | T522 | weather UI leaves `MapView.vue` | T521, fire T504 (panel hosts), its turn in the map chain | frontend-designer | breaker |

T520 and T521 are independent of each other and of every fire task except the shared assembly files. T522 is one link of the map chain.

**PR gate (every PR):** the gate of the fire plan, section 3. For T520 the smoke run includes step i. For T522 the manual look covers: the button row appears only on the satellite and offline basemaps, each of the four layers draws, the legend and the info panel show, the wind particles move and stop when the layer is switched off, and nothing is left running after leaving the map page.

## 4. Risks, rollback, not verified

| Risk | Mitigation |
|------|------------|
| The weather routes move from the end of the route table to the place of the module list (before `/ws`) | no path overlaps another route; only the order of the tag groups in `/docs` changes; stated in the PR body |
| The logger name `backend.routers.weather` becomes `backend.modules.weather.http` | no test names it (`test_api_weather.py:118` listens on `httpx`); stated in the PR body |
| `module_map.STEP_OF_MODULE` says `weather: 5` while the module exists after step 2 | it is data of the allowlist comments only; if an architecture test objects, the value is set to 2 in T520 and listed as an edit of test data |
| A module dictionary that writes into the core namespace `map` | `mergeMessages` merges deeply and the collision test fails on a key defined twice; if a rule of `modules.test.js` refuses it, the texts stay in the core files and the PR body says so |
| The panel is rendered at another place of the DOM than the canvas and the info panel are today | the `map` host is the last child of `.map-layout`, where both blocks already are; the wind canvas keeps its class and its place in the stacking order is checked by eye |
| The image of the weather icon is loaded from `openweathermap.org` (an internet URL in a system that must run offline) | it is today's behaviour and is not changed; noted for the owner in section 6 |

**Rollback.** `git revert -m 1 <merge commit>`, T522 before T521; T520 alone. No data.

**Not verified while planning:**
- Whether any `MapView*.test.js` queries the weather markup (the grep of section 2 is run in T522 step 1; if a test does and would need more than a path edit, the task stops).
- Whether `switchBasemap` (line 839) resets `weatherLayerId` when the basemap leaves satellite or offline: T522 step 1 reads it and the panel keeps exactly that behaviour.
- `import-linter` accepting a module with no `domain` and no `infrastructure` child in `check_boundary_contracts` (`forbidden_modules` = `http` and `module` only): T520 step 4.

## 5. Existing tests

All existing tests stay green without edits, except the files that move with their code in T521 (`lib/weatherTiles.test.js`, `lib/wind.test.js`: relative import paths). `backend/tests/test_api_weather.py` and `backend/tests/conftest.py` are not edited.

## 6. Open to the owner and hand-offs

1. **Weather was planned for step 5** (spec, section 5). It is brought forward because it shares no table and no backend dependency with anything; only the proxy file and the map UI move. The tile layer stays in the facade, as decided.
2. **The OWM client stays in `http.py`.** Splitting it into `infrastructure/owm.py` is a step 5 item together with the decision about the layer.
3. **TP-01.** The weather info panel loads its icon from `https://openweathermap.org/img/wn/...` and the wind fallback calls Open-Meteo from the browser. Both exist today and carry no personal data (a map area only, DP-01), but they are internet URLs outside the backend proxy. Not changed here; a question for the architecture owner.
4. **To the architecture owner (text proposal):** modular-monolith.md 4.1 lists `weather` as frontend only; after this plan it has a backend module without tables.

---

### Task 520: backend `weather` module

**risk:** security
**owner:** implementer
**Files:**
- Move (`git mv`): `backend/routers/weather.py` to `backend/modules/weather/http.py`
- Create: `backend/modules/weather/__init__.py` (docstring), `module.py`, `api.py` (docstring: the module offers nothing to other modules yet); the alias `backend/routers/weather.py`
- Modify: `backend/modules/registry.py` (one import and the name appended to `MODULES`), `backend/main.py` (the name `weather` leaves line 19; line 279 is deleted)
- Modify: `backend/tests/architecture/importlinter.toml`, `approved_additions.py`
- Modify: `tools/smoke.py`, `backend/tests/test_smoke_script.py`, `docs/SMOKE.md`
- Create: `backend/tests/modules/weather/__init__.py`, `backend/tests/modules/weather/test_weather_module.py`

**Interfaces:**
- Consumes: the loader with the route-type guard (fire T500), `check_boundary_contracts`, `check_manifest_wiring`.
- Produces `http.py`: the file as it is; its two relative imports become `from ...auth import get_current_user` and `from ...core.config import settings`.
- Produces `module.py`: `manifest = ModuleManifest(name='weather', router=http.router)` (no table, no task, no live message, no public route).
- Produces in `importlinter.toml`: the line `"backend.routers.weather -> backend.config"` is gone; new contract `id = "boundary-weather"`, `name = "module boundary: weather"`, `type = "forbidden"`, `source_modules` = `rules.LEGACY_SOURCES` plus every other `backend.modules.<name>` on disk, `forbidden_modules = ["backend.modules.weather.http", "backend.modules.weather.module"]`, `allow_indirect_imports = true`, `ignore_imports` with the one entry `"backend.routers.weather -> backend.modules.weather.http",  # until step 5` and its approval; `"backend.modules.weather"` is appended to the `source_modules` of every other `module boundary:` contract.
- Produces in `tools/smoke.py`: step `'i. GET /api/weather/current is served'`, `needs=('c. admin login + token refresh',)`; `s_weather` requests `GET /api/weather/current?lat=42.7&lon=23.3` with the token and passes on 200, 502 or 503 (503 is the answer of an environment without a key), fails on anything else.

- [ ] **Step 1: Write the failing tests** in `test_weather_module.py`, tagged `T520`: `test_old_router_path_is_the_module_http` (`backend.routers.weather is backend.modules.weather.http`, also through `from backend.routers import weather`); `test_importing_the_old_path_first_works` (subprocess, prints `backend.modules.weather.http`); `test_manifest` (name, no tables, `manifest.router is http.router`, `public_routes == ()`, in `MODULES`); `test_weather_routes_are_served_once_by_the_real_app` (the three `(path, methods)` pairs appear exactly once in `backend.main.app.routes`); `test_every_weather_route_needs_a_login` (`TestClient(backend.main.app)` without lifespan: the tile, `current` and `box` paths answer 401 without a token); `test_the_appid_filter_is_installed_by_importing_the_module_list` (subprocess: `import logging; from backend.modules import MODULES; print(any(type(f).__name__ == '_RedactAppid' for f in logging.getLogger('httpx').filters))` prints `True`); `test_openapi_operation_ids_are_unchanged` (`tile_api_weather_tiles__layer___z___x___y__png_get`, `current_api_weather_current_get`, `box_api_weather_box_get`); `test_main_no_longer_mounts_the_weather_router` (the text of `backend/main.py` has no `weather`). In `test_smoke_script.py`: `test_weather_step_passes_on_503_and_on_200` and `test_weather_step_fails_on_401`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules\weather -q`. Expected: FAIL with `ModuleNotFoundError: No module named 'backend.modules.weather'`.
- [ ] **Step 3: Move** the file, write the alias, the manifest, the registry line, the two `main.py` edits and the smoke step.
- [ ] **Step 4: Extend, then shrink the allowlist.** Add the contract, the alias line and its approval, the `source_modules` entries; run `.venv\Scripts\python backend\tests\architecture\regen.py --remove-stale` (it deletes the one stale line). Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\architecture -q`. Expected: PASS, including `test_every_contract_bites[module boundary: weather]`.
- [ ] **Step 5: Run** the module tests and the unedited proxy tests. Run: `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_api_weather.py backend\tests\test_smoke_script.py backend\tests\test_b49.py backend\tests\test_b51.py backend\tests\test_startup_migrations.py -q`. Expected: PASS.
- [ ] **Step 6: Commit** `refactor(weather): T520 the weather proxy becomes a backend module`. PR body: the logger name, the new place of the routes in the table, the allowlist arithmetic (1 deleted, 1 added).

dod:
- `cd bee-with-me; .venv\Scripts\python -m pytest backend\tests\modules backend\tests\architecture backend\tests\test_api_weather.py backend\tests\test_smoke_script.py backend\tests\test_b49.py backend\tests\test_b51.py backend\tests\test_startup_migrations.py -q`

### Task 521: frontend `weather` module, part 1 (libraries, texts, manifest)

**risk:** normal
**owner:** implementer
**Files:**
- Move (`git mv`): `frontend/src/lib/weatherTiles.js`, `lib/wind.js` and their two tests to `frontend/src/modules/weather/lib/`
- Create (re-exports, one statement each): `frontend/src/lib/weatherTiles.js`, `frontend/src/lib/wind.js`
- Create: `frontend/src/modules/weather/index.js`, `modules/weather/i18n/en.js`, `modules/weather/i18n/bg.js`, `modules/weather/index.test.js`
- Modify: `frontend/src/modules/index.js` (one line, alphabetical), `frontend/src/i18n/en.js`, `bg.js` (the weather keys of the `map` namespace leave)

**Interfaces:**
- Consumes: the module assembly of T403 (`modules/index.js`, the dictionary merge, `modules.test.js`).
- Produces `modules/weather/index.js`: `export default { name: 'weather', routes: [], nav: [], mapLayers: [], panels: [], banners: [], liveHandlers: {}, i18n: { en, bg }, depends: [] }`.
- Produces the module dictionaries: `{ map: { weather: {...}, weatherFeels: '...', ... } }` with exactly the keys and texts that leave the core files.

- [ ] **Step 1: Write the failing tests** in `modules/weather/index.test.js`, each `[T521]`: `the weather manifest is valid and is in the module list`; `the weather texts keep their keys in both languages` (every key of `keys.snapshot.json` that starts with `map.weather` exists in the merged EN and BG dictionaries and is no longer in the `core` export of `i18n/en.js`); `the old library paths are the moved libraries` (`recolorFor` imported from `lib/weatherTiles.js` and from `modules/weather/lib/weatherTiles.js` is one function; `windPoint` likewise).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/modules/weather/index.test.js`. Expected: FAIL (`Failed to resolve import "./index.js"`).
- [ ] **Step 3: Move** the libraries, write the re-exports, the manifest, the dictionaries and the list line.
- [ ] **Step 4: Run** the module checks and everything that imports the libraries. Run: `cd bee-with-me\frontend; npm test -- src/modules src/lib src/views src/i18n src/architecture.test.js; npm run build`. Expected: PASS and a clean build; `module lib is pure`, `no text key was lost` and `no key is defined twice` pass. If a rule refuses a module dictionary inside the `map` namespace, put the texts back into the core files, delete the first assertion of the second test and say so in the PR body.
- [ ] **Step 5: Commit** `refactor(weather): T521 weather libraries and texts move into the weather module`.

dod:
- `cd bee-with-me\frontend; npm test -- src/modules src/lib src/views src/i18n src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`

### Task 522: the weather buttons, panel and wind animation leave the map view

**risk:** normal
**owner:** frontend-designer
**Files:**
- Create: `frontend/src/modules/weather/layers.js`, `modules/weather/ui.js`, `modules/weather/components/WeatherToolbar.vue`, `modules/weather/components/WeatherPanel.vue`, `modules/weather/components/WeatherPanel.test.js`, `modules/weather/components/WeatherToolbar.test.js`
- Modify: `frontend/src/modules/weather/index.js` (`panels`)
- Modify: `frontend/src/views/MapView.vue` (the lines of section 1; the imports at 326, 329, 330; the weather lines of `onMounted` and `onUnmounted`)

**Interfaces:**
- Consumes: the hosts `map-toolbar` and `map` and the map context of fire T504 (`hostMap`, `facade`, `mapKit`, `activeBasemap`); `getWeatherCurrent`, `getWeatherBox` of `src/api`; the libraries of T521.
- Produces `layers.js`: `WEATHER_LAYERS` as it is in `MapView.vue` today. `ui.js`: a Pinia store `useWeatherUi` with `layerId` (`null` or a layer id) and `toggle(id)`.
- Produces in the manifest: `panels: [{ id: 'weather-toolbar', host: 'map-toolbar', order: 10, component: WeatherToolbar }, { id: 'weather-panel', host: 'map', order: 10, component: WeatherPanel }]`.
- Produces `WeatherToolbar.vue` (prop `context`): the row break and the four `bm-btn bm-btn-weather` buttons with their texts, shown only while `context.activeBasemap` is `satellite` or `offline`. `WeatherPanel.vue` (prop `context`): the wind canvas, the info panel and the legend with their present markup and classes; it owns `weatherInfo`, the debounce timer, `fetchWeather`, `fetchWindField` with its sources and the `boxCityDenied` flag, the particle animation and the `watch` on the layer id that calls `context.facade.setWeatherLayer(url, recolor)`; it attaches `moveend` when `context.hostMap` becomes a map (a watcher with `immediate`) and on unmount clears the timer, cancels the animation frame and removes the listener.
- Constraint: both components are imported statically by the manifest, so neither imports an `ol` module (the scanner of `modules.test.js:215` follows `.vue` files and is in this task's DoD). The moved code uses `toLonLat` for the bounding box and `unByKey` for the `moveend` listener today: it takes both from `context.mapKit`, or removes the listener with `map.un('moveend', handler)`.
- Produces in `MapView.vue`: no weather name is left; `setWeatherLayer` is still destructured from `useMap` only to be part of `facade`.

- [ ] **Step 1: Read, then write the failing tests.** Run the two greps of section 2 on the `MapView` tests and read `switchBasemap`. Tests, each `[T522]`, with a fake context (`facade: { setWeatherLayer: vi.fn() }`, `hostMap: shallowRef(null)`, `mapKit: { toLonLat: (c) => c, unByKey: vi.fn() }`, `activeBasemap: ref('osm')`) and `src/api` mocked: `WeatherToolbar.test.js`: `the buttons show only on the satellite and offline basemaps`; `a click switches the layer on and a second click switches it off`. `WeatherPanel.test.js`: `switching a layer on hands the tile URL and the recolour function to the map`; `switching it off clears the layer and the info panel`; `the panel attaches to a map that appears after mount` (set `hostMap.value = fakeMap`: `fakeMap.on` was called with `moveend`); `a move of the map fetches the weather once after the debounce`; `a denied box request falls back and is not repeated` (`getWeatherBox` resolves `{ denied: true }`: the wind source becomes `open-meteo` and a second fetch does not call `getWeatherBox`); `unmount stops the animation and removes the map listener` (`cancelAnimationFrame` and `fakeMap.un` were called, fake timers show no pending timer).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/modules/weather`. Expected: FAIL (`Failed to resolve import "./WeatherPanel.vue"`).
- [ ] **Step 3: Move** the blocks; the CSS rules of the moved elements move with them unchanged; the two re-exports of T521 stay in place until step 5.
- [ ] **Step 4: Run** the seven unedited `MapView` test files and the rest. Run: `cd bee-with-me\frontend; npm test -- src/modules src/views src/platform src/composables src/architecture.test.js; npm run build`. Expected: PASS and a clean build; the entry chunk size is in the PR body.
- [ ] **Step 5: Commit** `refactor(weather): T522 weather buttons, panel and wind animation are weather panels`.

dod:
- `cd bee-with-me\frontend; npm test -- src/modules src/views src/platform src/composables src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`
