# Vertical slices: map-shell extraction (contribution points for layers, banners, popups, context menu) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract a map shell into `frontend/src/platform/map-shell/` with four contribution points (map layers with z-order and toggle buttons, alarm banners by priority, popups on feature click, context-menu items) that module manifests fill, and route today's map features through those points, with no visible change.

**Architecture:** The shell owns the OpenLayers map, the z-order table, one exclusive "map mode" and the dispatch of click, pointer-move and context-menu events. `useMap.js` stays as a facade with today's signature and return value, so `MapView.vue` and the four `MapView*.test.js` files (which replace `useMap` with a mock) keep working unedited; inside, the facade builds the shell and installs contributions. Features that have no module yet (fire, tracking, SOS, repeaters) contribute through *legacy entries*: plain objects with the manifest shape that live next to today's code and move into the module's manifest in its own step. The first real manifest contribution is the HQ marker of the `settings` module (last task).

**Tech Stack:** Vue 3 `<script setup>`, OpenLayers 10, Pinia, vitest with `@vue/test-utils`, dependency-cruiser (existing). No new dependency.

**Spec:** [`docs/superpowers/specs/2026-10-31-vertical-slices-programme-design.md`](../specs/2026-10-31-vertical-slices-programme-design.md) (section 5 "Step 2", section 7 "Exact split of `useMap.js`": the `frontend-designer` decides within modular-monolith.md section 7), `Architecture/application/modular-monolith.md` sections 3.2, 3.3 and 7, ADR 17. Template and shared rules: [`2026-11-10-vs-step1-settings.md`](2026-11-10-vs-step1-settings.md) section 1. Wave overview: [`2026-11-10-vs-wave1-overview.md`](2026-11-10-vs-wave1-overview.md).

**Base:** `upstream/develop` at `2472543`. Execution branches: `feature/vs-map-<task>` off `develop`, one PR per task.

## Global Constraints

- **All tasks of this plan are executed by the `frontend-designer` agent** (dispatched with the Agent tool); hooks deny `.vue` and `.css` edits to anyone else. Each task is one PR that is green on its own.
- No visible change: same DOM structure, classes, `data-testid` and `data-layer` attributes, texts, z-order, click precedence, timers and keyboard behaviour. No new i18n key, no CSS change other than moving a rule with its element.
- `frontend/src/views/MapView.vue` keeps its path and file name (`AppLayout.vue` has `<KeepAlive include="MapView">`). `useMap(mapRef, positionList, trails, onCursorMGRS, onMeasure, groupsMap, onHQPlaced, showPhotos)` keeps its eight parameters and its 22 returned names.
- Every existing test stays green and unedited: `views/MapView.test.js`, `MapView.b52.test.js`, `MapView.b66.test.js`, `MapView.fire.test.js`, `composables/useMap.b50.test.js`, `useMap.b54.test.js`, `useMap.b56.test.js`, `useMap.fire.test.js`, `useMap.photo.test.js`, `useMap.zones.test.js`, `components/AppLayout.test.js`, `FireAlarmBanner.test.js`, `FirePopup.test.js`, `SOSBanner*.test.js`, `architecture.test.js`. Those tests are the proof of "no visible change"; a task that needs to edit one of them stops and reports.
- The shell (`src/platform/**`) imports no module and no legacy feature file (`platform-imports-no-module`); it receives contributions as arguments.
- No backend change, no WebSocket change, no `fire_alert*` payload change, no i18n file change, no dependency change. `frontend/src/architecture.allowlist.json` stays empty.
- Tags: vitest `it('... [T42x]', ...)`. Commits: `refactor(map): T42x summary`, body ends with the Co-Authored-By line of the session.

## Review Focus

1. Alarm order: the SOS banner is rendered above the fire banner whatever the order of the module list (BP-02). Pinned by priority numbers, not by array position (T421).
2. Click precedence on the map: release of a long press is swallowed, then HQ placement, repeater placement, measuring, tracker hit, fire hit, bare map. A dispatcher that lets two handlers act on one click would place HQ and open a popup at once (T422).
3. A contribution that throws while it is installed or while it handles an event must not take the map down: the shell logs it by contribution id and goes on with the others, so positions and SOS stay on screen (BP-01, BP-03) (T422).
4. The view can be unmounted while a mount is still awaiting, and `map()` can be `null` (as in `MapView.test.js`): the popup host and the context menu must tolerate a missing map and must remove their overlays and document listeners on unmount (T424, T425).
5. Layer toggles remembered from the last session show again after a reload, and the zones button stays admin-only (T426).

---

## 1. Contribution contract (what step 2 and later steps build on)

Manifest fields (`src/platform/manifest.js`, modular-monolith.md section 7). `mapLayers` and `banners` exist since T306; this plan adds the optional parts.

| Field | Item shape | Read by |
|-------|------------|---------|
| `mapLayers` | `{ id, zIndex, create?: (ctx) => olLayer, toggle?: { labelKey, order, adminOnly? } }` | the shell adds the layer with `zIndex`; `MapView` renders one button per `toggle`, sorted by `order` |
| `mapSetup` (optional function) | `(shell, ctx) => ({ api?, dispose? })`, called once after the module's layers are added | the shell; this is where a module registers click handlers, timers and its own functions |
| `banners` | `{ id, priority, component }` (lower priority is shown first) | `BannerStack.vue` in `AppLayout` |
| `popups` (optional) | `{ id, component, kinds: string[] }` | `MapPopupHost.vue` renders the component whose `kinds` contain the selection's `kind` |
| `contextMenu` (optional) | `{ id, order, labelKey, testId?, onSelect: ({ lonLat, coordinate }) => void }` | `MapContextMenu.vue` |

A **legacy entry** has exactly the shape of one item above plus a comment `// until step N`. It is defined beside the code it wraps and handed to the same collector as the manifests. Moving a feature into its module means moving the entry into the module's `index.js` and deleting it from the legacy list; nothing in the shell changes.

Z-order table (today's values from `useMap.js`, kept in one place, `src/platform/map-shell/zorder.js`): weather 2, burnt areas 3, suppression zones 3.4, hotspots 3.5, graticule 4, trail 5, checkpoints 6, trackers 10, repeaters 14, HQ 15, measure 20.

Priorities: SOS banner 10, fire alarm banner 20.

### How fire attaches in step 2 (prepared here, not done here)

| Fire piece today | After this plan | Step 2 does |
|------------------|-----------------|-------------|
| three layers, styles, hit test, 60 s repaint timer in `useMap.js` | `src/composables/map/fireLayers.js` exporting `FIRE_MAP_LAYERS` and `setupFireMap` (T423) | `git mv` to `src/modules/fire/map/`, list them in the fire manifest (`mapLayers`, `mapSetup`), delete the legacy install line in `useMap.js` |
| `FireAlarmBanner` in `AppLayout` | legacy banner entry, priority 20 (T421) | move the entry to the fire manifest `banners` |
| `FirePopup` and its overlay in `MapView` | legacy popup entry rendered by `MapPopupHost` (T424) | move the popup logic of `MapView.vue` (lines 491 to 616) into a fire container component and contribute it |
| "Report fire here" | legacy context-menu entry (T425) | move the entry to the fire manifest `contextMenu` |
| three toggle buttons | `toggle` on the three layer entries (T426) | nothing more |

The fire pill, the attribution line, the focus ring and the two fire dialogs stay in `MapView.vue` in this wave; step 2 owns them.

## 2. File map and who else touches each file (as of `2472543`)

Commands used: `git grep -nE "(from|import\() *'[^']*(composables/useMap|/useMap|nav-config|AppLayout|SOSBanner|FireAlarmBanner)" -- frontend/src`, `git grep -n "vi.mock(" -- "frontend/src/views/MapView*.test.js"`, `git diff --name-only upstream/develop...<branch>` for every unmerged branch.

| File | This plan | Also read or written by |
|------|-----------|-------------------------|
| `frontend/src/views/MapView.vue` (hot, 1580 lines) | T424, T425, T426 (one after the other) | plans 1 and 3 do not touch it; `main` holds B66 and B67 edits that `develop` lacks (owner's reconcile); four test files mount it with `useMap` mocked |
| `frontend/src/composables/useMap.js` (hot, 1108 lines) | T422, T423, T427 (one after the other) | plan 1 leaves a re-export at `composables/useSettings.js` so line 23 keeps working; plan 3 leaves one at `lib/groups.js` (line 24); six `useMap.*.test.js` files call the real composable |
| `frontend/src/components/AppLayout.vue` | T421 | plan 1 changes `nav-config.js`, which it imports, not the file itself; `AppLayout.test.js` stubs `SOSBanner` and `FireAlarmBanner` by name |
| `frontend/src/platform/manifest.js` | T420 (optional fields) | `architecture.test.js` (T306 test of the required fields); plan 1's `platform/registry.js` calls `validateManifest` |
| `frontend/src/modules/index.js` | read by T421, T422, T424, T425, T426; not edited | created by plan 1 (T403); edited by T404 and plan 3 |
| `frontend/src/modules/settings/index.js` | T427 adds `mapLayers` and `mapSetup` | created by plan 1 (T404) |
| new: `frontend/src/platform/map-shell/{contributions,zorder,createMapShell}.js`, `BannerStack.vue`, `MapPopupHost.vue`, `MapContextMenu.vue`, tests next to them | T420 to T425 | step 2 and later steps read them |
| new: `frontend/src/components/legacyBanners.js`, `frontend/src/composables/map/fireLayers.js`, `frontend/src/modules/settings/map/hqLayer.js` | T421, T423, T427 | step 2 moves the first two |

Not touched: `i18n/en.js`, `bg.js`, `router/index.js`, `nav-config.js`, `stores/*`, `api/*`, `style.css`, every backend file, `importlinter.toml`, `allowlist.json`, `main.py`.

## 3. Task order, PRs, reviewers, parallel work

| PR | Task | Content | Needs | Reviewers |
|----|------|---------|-------|-----------|
| 1 | T420 | contribution collectors, z-order table, optional manifest fields | nothing | breaker |
| 2 | T421 | banner point in `AppLayout` | T420, T403 | breaker |
| 3 | T422 | shell core under the `useMap` facade | T420 | breaker |
| 4 | T423 | fire layers as a contribution file | T422 | breaker |
| 5 | T424 | popup point in `MapView` | T420, T403 | breaker |
| 6 | T425 | context-menu point in `MapView` | T424 | breaker |
| 7 | T426 | layer toggle buttons from contributions | T425, T423 | breaker |
| 8 | T427 | HQ marker as the `settings` module's layer | T423, T404 | breaker |

No file of this plan is on the security-critical list (`src/api/**`, `src/router/**`, `stores/auth.js`, `package.json`, `vite.config.js`), so the `security-reviewer` is not required; if a task turns out to need one of those files it stops and reports.

**Inside the plan.** T420 first. Then two chains that never share a file and run in parallel: chain U (`useMap.js`): T422, T423, T427; chain V (`MapView.vue`): T424, T425, T426. T421 (`AppLayout.vue`) is parallel to both. T426 is the one join: it reads the `toggle` data T423 puts on the fire layer entries, so it starts after T423 is merged. Never run two tasks of one chain at the same time: `MapView.vue` and `useMap.js` are single large files and a parallel edit of either is a hand merge of a 1500-line file.

**Against the other two plans.** T421, T422, T424, T425 and T426 import `MODULES` from `src/modules/index.js`, which plan 1 creates in T403: T403 is merged first (T420 does not need it). Plan 1 and plan 3 edit neither `MapView.vue`, `useMap.js` nor `AppLayout.vue`. The only shared file is `src/modules/settings/index.js` (T404 creates it, T427 adds two fields): T427 runs after T404, no conflict. If the owner merges `main` into `develop` (B66, B67 in `MapView.vue`) while a chain V task is open, merge `upstream/develop` into the branch and rerun the four `MapView*.test.js` files; do not rebase.

**PR gate (every PR), in this order:** (1) the task's DoD; (2) `cd bee-with-me\frontend; npm test; npm run build`; (3) `python tools/smoke.py` (step f builds the frontend image and serves the SPA), PASS lines in the PR body; (4) a manual look at the map in the dev stack by the maintainer for the element the task moved (banner order, popup position, context menu, toggle buttons, HQ marker), listed as a checkbox in the PR body, and a reminder to run the impeccable detector; (5) `breaker` on the head commit until `VERDICT: PASS`; (6) `gh pr create` is run by the human with `--body-file`.

## 4. Risks, rollback, not verified

| Risk | Mitigation |
|------|------------|
| The tests mock `useMap` entirely, so `MapView` tests cannot see a facade mistake, and the `useMap` tests cannot see a `MapView` mistake | each chain is covered by its own six or four test files; the manual check of the PR gate covers the seam; T422 adds shell tests for precedence and error isolation |
| One exclusive map mode replaces three booleans (`hqPlacementMode`, `repeaterPlacementMode`, `measureMode`) | `MapView` already switches the other modes off when one starts; T422 pins the precedence with all three requested at once; if a `useMap.*.test.js` needs two modes on together, keep the booleans inside the facade and report |
| `vi.mock('ol/Overlay')` and `vi.mock('ol/proj')` apply to every importer in the four `MapView` test files | the new `.vue` hosts import only what `MapView.vue` imports today (`ol/Overlay`, `ol/proj`); layer code with other `ol` imports stays behind the mocked `useMap` |
| A banner rendered through `<component :is>` is not stubbed by name in `AppLayout.test.js` | T421 step 4 runs that test first; fallback: `BannerStack` renders the legacy entries through named components and the dynamic path only for manifest entries |
| `KeepAlive` loses the map when the component name changes | `MapView.vue` is not renamed or wrapped |
| Performance: more indirection per pointer move | handlers are plain function calls in a short array; no reactive state is added on the pointer path |
| bee-dev shows a broken map | smoke builds the image but opens no browser: the manual check in the PR gate is mandatory for this plan |

**Rollback.** Frontend only, no data: `git revert -m 1 <merge commit>`, newest first inside a chain (T427, T423, T422 and T426, T425, T424); T421 alone; T420 last.

**Not verified while planning (the executor checks it in the named step):**
- That `@vue/test-utils` stubs a component by name when it is rendered through `<component :is>` inside a child component (T421 step 4).
- That every `useMap.*.test.js` passes with the map built by the shell instead of inline (T422 step 4); they were read only at the level of their set-up (`mountMap()` calls the real composable in jsdom).
- The exact markup the `MapView` tests query for the popup anchor and the context menu beyond `data-testid="report-fire-here"`, `.map-context`, `.mc-item`, `.fire-popup-anchor` (T424, T425 step 1: read the four test files before moving markup).
- That a manifest which imports OpenLayers code can be loaded in the four `MapView` test files, where `ol/proj` is mocked with two functions only (T427 step 4: after T427 `MapView.vue` reaches `modules/settings/map/hqLayer.js` through `MODULES`). Fallback if they fail with `No "<name>" export is defined on the "ol/proj" mock`: the manifest declares the layer without `create` (`{ id: 'settings-hq', zIndex: Z.hq }`) and has no `mapSetup`; the facade `useMap.js`, which those tests mock, imports `hqLayer.js` and installs `{ name: 'settings', mapLayers: [HQ_LAYER], mapSetup: setupHQMap }` itself. Say which variant shipped in the PR body.
- No browser was opened while planning.

## 5. Existing tests

Listed in Global Constraints; none is edited, not even for import paths (no tested file moves in this plan). New tests sit next to the new files.

## 6. Open to the owner and hand-offs

1. **Scope of the shell in this wave.** Tracker markers, trails, checkpoints, repeaters, the graticule, measuring, the weather layer and the basemaps stay inside the `useMap` facade and are only registered through the shell (z-order, events). They move out with `tracking` (step 3), `devices` (step 4), `weather` and `maps` (step 5). Confirm, or ask for the tracker layers now (one more task in chain U).
2. **The tracker side panel** (modular-monolith.md section 7, "side panels") is not made a contribution point here; it is `tracking`'s (step 3).
3. **The `offline-map-changed` window event** in `MapView.vue` stays; the spec moves it into a `maps` contribution in step 5.
4. **To the architecture owner (text proposal, not edited here):** modular-monolith.md section 7 gets the contract table of section 1 (`mapSetup`, `popups`, `contextMenu`, `toggle`), the z-order table and the banner priorities.
5. **Banner priorities** 10 (SOS) and 20 (fire) leave room for future alarms; a future generic field signal (FX-04) needs a number from the owner.

---

### Task 420: contribution collectors, z-order table and optional manifest fields

**risk:** normal
**owner:** frontend-designer
**Files:**
- Create: `frontend/src/platform/map-shell/contributions.js`, `frontend/src/platform/map-shell/zorder.js`
- Modify: `frontend/src/platform/manifest.js` (optional fields only; a manifest that is valid today stays valid)
- Test: `frontend/src/platform/map-shell/contributions.test.js`

**Interfaces:**
- Consumes: `validateManifest` (existing).
- Produces in `zorder.js`: `export const Z = Object.freeze({ weather: 2, burnt: 3, zones: 3.4, hotspots: 3.5, graticule: 4, trail: 5, checkpoints: 6, trackers: 10, repeaters: 14, hq: 15, measure: 20 })` and `export const BANNER_PRIORITY = Object.freeze({ sos: 10, fireAlarm: 20 })`.
- Produces in `contributions.js` (pure; each function takes `(modules, legacy = [])`, where `modules` are manifests and `legacy` are items of the same shape):
  - `collectBanners(modules, legacy) -> item[]` sorted by `priority`, then `id`.
  - `collectMapLayers(modules, legacy) -> item[]` sorted by `zIndex`, then `id`.
  - `collectLayerToggles(modules, legacy) -> { id, labelKey, order, adminOnly }[]`: one per layer item that has `toggle`, sorted by `order`.
  - `collectPopups(modules, legacy) -> item[]`; `popupFor(popups, kind) -> item | null` (the first whose `kinds` contain `kind`).
  - `collectContextMenu(modules, legacy) -> item[]` sorted by `order`, then `id`.
  - `contributionProblems(modules, legacy) -> string[]`: an `id` used twice within one kind, two banners with the same `priority`, a popup `kind` claimed twice.
- Produces in `manifest.js`: `validateManifest` also checks, only when the field is present: `mapSetup` is a function; `popups` is an array of `{ id: text, component, kinds: non-empty array of text }`; `contextMenu` is an array of `{ id: text, order: finite number, labelKey: text, onSelect: function }`; a `mapLayers` item's `create` is a function and its `toggle` is `{ labelKey: text, order: finite number }`.

- [ ] **Step 1: Write the failing tests**, each `[T420]`: `banners come out by priority whatever the list order` (modules `[fire(20), sos(10)]` and the reverse both give `['sos', 'fire']`); `legacy entries and manifest entries are merged` (one of each kind); `map layers come out by zIndex` (3.5, 3, 3.4 gives 3, 3.4, 3.5); `layer toggles come out by order and carry adminOnly`; `popupFor picks by kind and returns null for an unknown kind`; `context menu items come out by order`; `contributionProblems names a duplicate id, a duplicate banner priority and a kind claimed twice`; `validateManifest accepts the optional fields and names each malformed one` (a complete manifest with `mapSetup`, `popups`, `contextMenu`, a layer with `create` and `toggle` gives `[]`; `mapSetup: 1`, a popup without `kinds`, a menu item without `onSelect`, a toggle without `order` each give a message containing the field name); `Z and BANNER_PRIORITY hold today's values` (the two literals above).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/platform/map-shell/contributions.test.js`. Expected: FAIL (`Failed to resolve import "./contributions.js"`).
- [ ] **Step 3: Implement** the interfaces.
- [ ] **Step 4: Run** the new test and the architecture test (its T306 case checks the required manifest fields). Run: `cd bee-with-me\frontend; npm test -- src/platform src/architecture.test.js`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(map): T420 contribution collectors and the z-order table`.

dod:
- `cd bee-with-me\frontend; npm test -- src/platform src/architecture.test.js`

### Task 421: banner point in the layout

**risk:** normal
**owner:** frontend-designer
**Files:**
- Create: `frontend/src/platform/map-shell/BannerStack.vue`, `frontend/src/components/legacyBanners.js`
- Modify: `frontend/src/components/AppLayout.vue` (the two banner tags and their two imports)
- Test: `frontend/src/platform/map-shell/BannerStack.test.js`

**Interfaces:**
- Consumes: `collectBanners`, `BANNER_PRIORITY` (T420); `MODULES` from `src/modules/index.js` (plan 1, T403).
- Produces: `BannerStack.vue` with one prop `banners` (array of `{ id, priority, component }`, already sorted); it renders each `component` in order with `:key="id"` and no wrapper element (a fragment), so the DOM under `<main class="main-content">` is what it is today.
- Produces in `legacyBanners.js`: `export const LEGACY_BANNERS = [{ id: 'sos', priority: BANNER_PRIORITY.sos, component: SOSBanner }, { id: 'fire-alarm', priority: BANNER_PRIORITY.fireAlarm, component: FireAlarmBanner }]`, with the comments `// until step 3` and `// until step 2`.
- Produces in `AppLayout.vue`: `<BannerStack :banners="banners" />` in place of `<SOSBanner />` and `<FireAlarmBanner />`, with `const banners = collectBanners(MODULES, LEGACY_BANNERS)`. Everything else in the file is unchanged (the `useFireStore` use in `onMounted` stays).

- [ ] **Step 1: Write the failing tests**, each `[T421]`: `renders banners in the given order without a wrapper` (two stub components with root classes `a` and `b`; the mounted stack's HTML has `a` before `b` and the stack adds no element of its own); `the legacy list puts SOS above fire` (`collectBanners([], LEGACY_BANNERS).map(b => b.id)` equals `['sos', 'fire-alarm']`); `a module banner with priority 15 lands between them` (a fixture manifest; ids `['sos', 'x', 'fire-alarm']`); `the layout shows SOS above the fire alarm` (mount `AppLayout` as `AppLayout.test.js` does, with `SOSBanner` and `FireAlarmBanner` stubbed by name; inside `.main-content` the SOS stub element comes before the fire stub element).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/platform/map-shell/BannerStack.test.js`. Expected: FAIL (`Failed to resolve import "./BannerStack.vue"`).
- [ ] **Step 3: Implement** the stack, the legacy list and the `AppLayout.vue` edit.
- [ ] **Step 4: Run** the unedited layout and banner tests first, then the new ones. Run: `cd bee-with-me\frontend; npm test -- src/components src/platform/map-shell; npm run build`. Expected: PASS and a clean build. If the name stubs of `AppLayout.test.js` do not apply through `<component :is>`, use the fallback of section 4 and say so in the PR body.
- [ ] **Step 5: Commit** `refactor(map): T421 alarm banners come from contributions, ordered by priority`.

dod:
- `cd bee-with-me\frontend; npm test -- src/components src/platform/map-shell`
- `cd bee-with-me\frontend; npm run build`

### Task 422: shell core under the `useMap` facade

**risk:** normal
**owner:** frontend-designer
**Files:**
- Create: `frontend/src/platform/map-shell/createMapShell.js`
- Modify: `frontend/src/composables/useMap.js` (map construction, the two `click` handlers, the two `pointermove` handlers, the context-menu and long-press wiring, the three mode booleans, the `zIndex` literals)
- Test: `frontend/src/platform/map-shell/createMapShell.test.js`

**Interfaces:**
- Consumes: `Z` (T420); `collectMapLayers` (T420); `createLongPress` from `src/lib/longPress.js` (passed in by the facade: the shell does not import `src/lib`).
- Produces `createMapShell({ target, view, controls, overlays, longPress }) -> shell` (plain JavaScript, no Vue import):
  - `shell.map`: the `ol/Map`.
  - `shell.addLayer({ id, zIndex, layer })`: sets the z-index on the layer and adds it; a second layer with the same `id` throws `Error('map layer <id> is already registered')`. `shell.layer(id)` returns it or `undefined`.
  - `shell.install(contribution, ctx) -> api`: for each `mapLayers` item with `create`, `addLayer({ id, zIndex, layer: create(ctx) })`; then `mapSetup?.(shell, ctx)`; returns the `api` of the setup or `{}`; keeps `dispose` for `shell.dispose()`. An exception from `create` or `mapSetup` is caught, logged as `console.error('map contribution <name or id> failed to install', error)` and the install of the others goes on.
  - `shell.setMode(name | null)`, `shell.mode()`: one exclusive mode.
  - `shell.onClick(handler, { mode, order = 100 })` and `shell.onPointerMove(handler, { mode, order = 100 })` return an unsubscribe function. On an event: if the long press reports `shouldSwallowClick()`, a click goes to nobody; otherwise handlers registered for the current mode run, or, when the mode is `null`, the handlers without a mode run in `order`; a click handler that returns `true` stops the ones after it; a handler that throws is logged by its order and skipped. Dragging pointer moves are not dispatched.
  - `shell.onContextMenu(handler)`: called with `{ coordinate, pixel }` for a right click or a long press, once per gesture (800 ms de-duplication), and only when the mode is `null`.
  - `shell.dispose()`: disposes contributions, removes the viewport listeners, calls `map.setTarget(null)`.
- Produces in `useMap.js`: the same eight parameters and 22 returned names. Inside, the map is built by `createMapShell`; every layer is added through `shell.addLayer` with a value of `Z`; `setHQPlacementMode(on)`, `setRepeaterPlacementMode(on)` and `setMeasureMode(on)` set the modes `'hq-place'`, `'repeater-place'`, `'measure'` (switching one off clears the mode only when it is the current one); the tracker and fire click logic become mode-less click handlers (tracker `order` 10, fire `order` 20, with the bare-map case closing the popup and deselecting as today); `onMapContextMenu(cb)` forwards to `shell.onContextMenu`. After its own layers the facade calls `shell.install(m, ctx)` for every manifest in `MODULES` (none contributes a layer yet).

- [ ] **Step 1: Write the failing tests** in `createMapShell.test.js`, each `[T422]`, against a real `ol/Map` in jsdom with `target: document.createElement('div')` (the set-up `useMap.fire.test.js` uses, including the `ResizeObserver` shim): `layers get the z-index of their registration and a duplicate id throws`; `install adds the layers, runs mapSetup and returns its api`; `a contribution that throws in create or in mapSetup is logged and the next one is still installed` (spy on `console.error`); `mode handlers win over mode-less ones` (mode `'measure'`: only the `measure` handler runs on a dispatched click); `mode-less click handlers run in order and stop at the first that returns true` (orders 20 and 10 registered in that sequence; the order-10 handler returns `true`; the order-20 handler is not called); `a click after a long press reaches no handler` (`longPress.shouldSwallowClick` returns `true`); `a throwing click handler is logged and the next one runs`; `the context menu is reported once per gesture and not while a mode is active`; `dispose removes the target and calls every dispose`. Clicks are dispatched with `shell.map.dispatchEvent({ type: 'click', pixel: [1, 1], coordinate: [0, 0] })`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/platform/map-shell/createMapShell.test.js`. Expected: FAIL (`Failed to resolve import "./createMapShell.js"`).
- [ ] **Step 3: Implement the shell, then switch the facade to it** in this order, running the six `useMap.*.test.js` files after each: map construction and `addLayer`; modes; click and pointer-move dispatch; context menu and long press; unmount through `shell.dispose()`.
- [ ] **Step 4: Run** the shell tests, the six unedited `useMap` test files, the four `MapView` test files and the architecture test. Run: `cd bee-with-me\frontend; npm test -- src/platform src/composables src/views src/architecture.test.js; npm run build`. Expected: PASS and a clean build.
- [ ] **Step 5: Commit** `refactor(map): T422 the map shell owns the map, the z-order, the mode and event dispatch`.

dod:
- `cd bee-with-me\frontend; npm test -- src/platform src/composables src/views src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`

### Task 423: fire layers as a contribution file

**risk:** normal
**owner:** frontend-designer
**Files:**
- Create: `frontend/src/composables/map/fireLayers.js`
- Modify: `frontend/src/composables/useMap.js` (the fire styles, sources, layers, hit test, repaint timer and the six fire functions leave the file; one install line and six delegating names stay)
- Test: `frontend/src/composables/map/fireLayers.test.js`

**Interfaces:**
- Consumes: `shell.install`, `shell.onClick`, `shell.onPointerMove`, `shell.layer` (T422); `Z` (T420); `lib/fireStyle.js`, `lib/color.js` (unchanged).
- Produces in `fireLayers.js`:
  - `export const FIRE_MAP_LAYERS = [{ id: 'fire-burnt', zIndex: Z.burnt, create, toggle: { labelKey: 'fire.layers.burnt', order: 10 } }, { id: 'fire-zones', zIndex: Z.zones, create, toggle: { labelKey: 'fire.layers.zones', order: 30, adminOnly: true } }, { id: 'fire-hotspots', zIndex: Z.hotspots, create, toggle: { labelKey: 'fire.layers.hotspots', order: 20 } }]`. The button order (burnt, hotspots, zones) and the label keys are today's `FIRE_LAYER_BUTTONS` in `MapView.vue`: read them there and keep them.
  - `export function setupFireMap(shell, ctx) -> { api: { setBurntAreas, setHotspots, setZones, setFireLayerVisible, setFireLabels, onFireFeatureClick }, dispose }`, with the behaviour of today's functions of the same names (`setHotspots` and `setBurntAreas` return `false` for unreadable GeoJSON and keep the previous features; layers start hidden; hotspots repaint every 60 s while visible; the fire click handler is mode-less with `order` 20 and reports `{ kind, properties, coordinate }` or `null`; `ctx.trackerHit(pixel)` lets a tracker win).
  - `export const LEGACY_FIRE_MAP = { name: 'fire', mapLayers: FIRE_MAP_LAYERS, mapSetup: setupFireMap }` with the comment `// until step 2`.
- Produces in `useMap.js`: `const fire = shell.install(LEGACY_FIRE_MAP, ctx)` and the six returned names delegate to `fire`.

- [ ] **Step 1: Write the failing tests**, each `[T423]`, with a shell on a real map as in T422: `the three fire layers are registered with z-index 3, 3.4 and 3.5 and start hidden`; `setHotspots keeps the previous features and returns false for unreadable GeoJSON` (`setHotspots({ type: 'FeatureCollection', features: 1 })`); `setFireLayerVisible shows one layer by name` (names `burnt`, `hotspots`, `zones`); `each layer entry carries the toggle of its button` (`collectLayerToggles([], FIRE_MAP_LAYERS)` gives the ids `fire-burnt`, `fire-hotspots`, `fire-zones` in that order and only `fire-zones` is `adminOnly`); `dispose stops the repaint timer` (fake timers: after `dispose()` advancing 60 s calls `changed()` on no layer).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/composables/map/fireLayers.test.js`. Expected: FAIL (`Failed to resolve import "./fireLayers.js"`).
- [ ] **Step 3: Move** the fire code out of `useMap.js` into the new file without changing a style value, a hit tolerance (6 px for hotspots) or a message; wire the install line and the six delegating names.
- [ ] **Step 4: Run** the new tests and the unedited fire and zone tests of the facade. Run: `cd bee-with-me\frontend; npm test -- src/composables src/platform src/views src/architecture.test.js; npm run build`. Expected: PASS and a clean build.
- [ ] **Step 5: Commit** `refactor(map): T423 fire layers are one contribution, ready to move in step 2`.

dod:
- `cd bee-with-me\frontend; npm test -- src/composables src/platform src/views src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`

### Task 424: popup point in the map view

**risk:** normal
**owner:** frontend-designer
**Files:**
- Create: `frontend/src/platform/map-shell/MapPopupHost.vue`
- Modify: `frontend/src/views/MapView.vue` (the `fire-popup-anchor` block of the template, the `fireOverlay` creation in the first `onMounted`, its removal in `onUnmounted`, the positioning in the `onFireFeatureClick` callback)
- Test: `frontend/src/platform/map-shell/MapPopupHost.test.js`

**Interfaces:**
- Consumes: `collectPopups`, `popupFor` (T420); `MODULES` (T403); `map()` and `onFireFeatureClick` of the `useMap` facade (unchanged names).
- Produces `MapPopupHost.vue`: props `map` (an `ol/Map` or `null`), `popups` (collected list), `selection` (`{ kind, coordinate, ... } | null`), `anchorClass` (string). It owns one `ol/Overlay` (`positioning: 'bottom-center'`, `offset: [0, -16]`, `stopEvent: true`, `autoPan` with a 200 ms animation and a 24 px margin, 0 ms when `prefers-reduced-motion: reduce` matches) on an element with `anchorClass`; it renders the default slot inside that element, passing `{ popup, selection }` (`popup` is `popupFor(popups, selection.kind)`); after the content is rendered (`nextTick`) it sets the overlay position to `selection.coordinate`, or to `undefined` without a selection; it removes the overlay from the map on unmount; with `map === null` it renders the anchor and does nothing else.
- Produces in `MapView.vue`: a legacy popup entry `{ id: 'fire', component: FirePopup, kinds: ['hotspot', 'burnt_area'] }` (`// until step 2`) collected with `collectPopups(MODULES, [entry])`; the host is used with `anchor-class="fire-popup-anchor"` and its slot renders the popup component with exactly today's props and listeners (`kind`, `properties`, `lon-lat`, `is-admin`, `busy`, `error-text`, `close`, `dismiss`, `extinguish`, `create-zone`). The focus ring keeps its own overlay in `MapView.vue`.

- [ ] **Step 1: Read, then write the failing tests.** Read the four `MapView*.test.js` files for every query on the popup (`.fire-popup-anchor`, the `FirePopup` stub, `addOverlay`, `removeOverlay`, `setPosition`) and keep each queried element and call. Tests, each `[T424]`, with a fake map `{ addOverlay: vi.fn(), removeOverlay: vi.fn() }` and `ol/Overlay` mocked as a class recording `setPosition` calls: `adds one overlay on mount and removes it on unmount`; `renders the slot with the popup that claims the selection kind` (popups for `a` and `b`; selection kind `b`); `positions the overlay after the content is rendered and clears it when the selection goes` (`setPosition` called with the coordinate, later with `undefined`); `an unknown kind renders nothing and clears the position`; `a null map renders the anchor and touches no overlay`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/platform/map-shell/MapPopupHost.test.js`. Expected: FAIL (`Failed to resolve import "./MapPopupHost.vue"`).
- [ ] **Step 3: Implement** the host and replace the popup block and its overlay handling in `MapView.vue`. The CSS rule of `.fire-popup-anchor` moves with the element only if it is scoped to it.
- [ ] **Step 4: Run** the four unedited `MapView` test files, the popup component test and the new test. Run: `cd bee-with-me\frontend; npm test -- src/views src/components/FirePopup.test.js src/platform src/architecture.test.js; npm run build`. Expected: PASS and a clean build.
- [ ] **Step 5: Commit** `refactor(map): T424 popups on feature click come from contributions`.

dod:
- `cd bee-with-me\frontend; npm test -- src/views src/components/FirePopup.test.js src/platform src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`

### Task 425: context-menu point in the map view

**risk:** normal
**owner:** frontend-designer
**Files:**
- Create: `frontend/src/platform/map-shell/MapContextMenu.vue`
- Modify: `frontend/src/views/MapView.vue` (the `map-context` block of the template; `ctxMenu`, `ctxMenuEl`, `openContextMenu`, `closeContextMenu`, `onOutsidePointer`, `onMenuKey`, `reportFromMenu` in the script, lines 658 to 692)
- Test: `frontend/src/platform/map-shell/MapContextMenu.test.js`

**Interfaces:**
- Consumes: `collectContextMenu` (T420); `MODULES` (T403); `onMapContextMenu` of the facade (unchanged).
- Produces `MapContextMenu.vue`: prop `items` (collected list); exposed methods `open({ coordinate, pixel, bounds: { width, height } })` and `close()`; it renders, only while open and only when `items` is not empty, `<div class="map-context" role="menu">` positioned at the pixel and kept inside the bounds with today's arithmetic (`x = max(4, min(pixel[0], width - 196))`, `y = max(4, min(pixel[1], height - 52))`, the raw pixel when a bound is 0), one `<button type="button" role="menuitem" class="mc-item" :data-testid="item.testId">` per item with the text `t(item.labelKey)`; opening focuses the first button after `nextTick`; a pointer-down outside the menu or the Escape key closes it (document listeners in the capture phase, added on the first open and removed on close and on unmount); choosing an item calls `item.onSelect({ coordinate, lonLat: toLonLat(coordinate) })` and closes.
- Produces in `MapView.vue`: a legacy item `{ id: 'fire-report-here', order: 10, labelKey: 'fire.report.here', testId: 'report-fire-here', onSelect: ({ lonLat }) => openDialog({ kind: 'report', target: { latitude: lonLat[1], longitude: lonLat[0] } }) }` (`// until step 2`); `onMapContextMenu((e) => menu.value?.open({ ...e, bounds }))`; the unmount path still calls `onMapContextMenu(null)`.

- [ ] **Step 1: Read, then write the failing tests.** Read `MapView.fire.test.js` and `MapView.b52.test.js` for every query on the menu (`[data-testid="report-fire-here"]`, `.map-context`, focus, Escape, the dialog that opens) and keep each. Tests, each `[T425]`: `closed by default and with no items it never opens`; `open shows one menu item per contribution in order with its test id and label`; `the menu stays inside the bounds` (pixel `[500, 400]` in bounds `600 x 420` gives `left: 404px; top: 368px`; pixel `[1, 1]` gives `4px` and `4px`); `the first item is focused after opening`; `Escape and an outside pointer-down close it and remove the document listeners` (spy on `document.removeEventListener`); `choosing an item calls onSelect with the coordinate and its lon/lat and closes`; `unmount while open removes the document listeners`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/platform/map-shell/MapContextMenu.test.js`. Expected: FAIL (`Failed to resolve import "./MapContextMenu.vue"`).
- [ ] **Step 3: Implement** the component and replace the block and the seven script members in `MapView.vue`. The `.map-context` and `.mc-item` CSS rules move into the component unchanged.
- [ ] **Step 4: Run** the four unedited `MapView` test files and the new test. Run: `cd bee-with-me\frontend; npm test -- src/views src/platform src/architecture.test.js; npm run build`. Expected: PASS and a clean build.
- [ ] **Step 5: Commit** `refactor(map): T425 map context-menu items come from contributions`.

dod:
- `cd bee-with-me\frontend; npm test -- src/views src/platform src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`

### Task 426: layer toggle buttons from contributions

**risk:** normal
**owner:** frontend-designer
**Files:**
- Modify: `frontend/src/views/MapView.vue` (the `v-for="name in fireLayerButtons"` button of the template; `FIRE_LAYER_BUTTONS`, `fireLayerButtons`, `toggleFire`, `ensureLayer` and the remembered-layers loop in the first `onMounted`)
- Test: `frontend/src/views/MapView.toggles.test.js`

**Interfaces:**
- Consumes: `collectLayerToggles` (T420); `FIRE_MAP_LAYERS` (T423); `MODULES` (T403); `setFireLayerVisible` of the facade; `fireStore.layers` (unchanged).
- Produces in `MapView.vue`: `const layerToggles = computed(() => collectLayerToggles(MODULES, FIRE_MAP_LAYERS).filter(t => !t.adminOnly || isAdmin.value))`; the template renders one button per toggle with today's attributes (`class="bm-btn"` plus `active`, `:aria-pressed`, `:data-layer`, the text `t(toggle.labelKey)`); a local map from the toggle id to today's layer name (`fire-burnt` to `burnt`, `fire-hotspots` to `hotspots`, `fire-zones` to `zones`, `// until step 2`) keeps `data-layer`, `fireStore.layers[name]` and `setFireLayerVisible(name, on)` exactly as they are.

- [ ] **Step 1: Read, then write the failing tests.** Read `MapView.fire.test.js` for the queries on `[data-layer]` and on `hooks.layerVisible`. New file with the mock set-up of `MapView.fire.test.js` (copied, that file is not edited), each `[T426]`: `an admin sees burnt, hotspots, zones in that order and a viewer does not see zones` (the `data-layer` values of the rendered buttons); `a click toggles the store flag and tells the map` (`fireStore.layers.hotspots` flips and `hooks.layerVisible` ends with `['hotspots', true]`); `layers remembered from the last session are shown on mount, zones only for an admin`; `the labels come from the contribution` (button texts equal `en.fire.layers.burnt`, `en.fire.layers.hotspots`, `en.fire.layers.zones`).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/views/MapView.toggles.test.js`. Expected: FAIL on the fourth test only until the buttons read `labelKey` (the first three pin today's behaviour and pass before the change; say so in the commit message).
- [ ] **Step 3: Implement** the computed list and the template change.
- [ ] **Step 4: Run** all `MapView` test files. Run: `cd bee-with-me\frontend; npm test -- src/views src/platform src/composables src/architecture.test.js; npm run build`. Expected: PASS and a clean build.
- [ ] **Step 5: Commit** `refactor(map): T426 layer toggle buttons come from the layer contributions`.

dod:
- `cd bee-with-me\frontend; npm test -- src/views src/platform src/composables src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`

### Task 427: the HQ marker is the `settings` module's map layer (first real manifest contribution)

**risk:** normal
**owner:** frontend-designer
**Files:**
- Create: `frontend/src/modules/settings/map/hqLayer.js`
- Modify: `frontend/src/modules/settings/index.js` (`mapLayers` and `mapSetup`)
- Modify: `frontend/src/composables/useMap.js` (`hqSource`, `hqLayer`, `makeHQStyle`, `setHQ`, `setHQPlacementMode` and the HQ branch of the click handling leave the file; two delegating names stay)
- Test: `frontend/src/modules/settings/map/hqLayer.test.js`

**Interfaces:**
- Consumes: `shell.install(m, ctx)` for every manifest of `MODULES` (T422); `Z.hq` (T420); the `settings` manifest (plan 1, T404); the facade's seventh parameter `onHQPlaced`.
- Produces in `hqLayer.js`: `export const HQ_LAYER = { id: 'settings-hq', zIndex: Z.hq, create }` and `export function setupHQMap(shell, ctx) -> { api: { setHQ(loc, label), setHQPlacementMode(on) }, dispose }`: `setHQ` draws or clears the marker with today's style and default label `'ЩАБ'`; `setHQPlacementMode(true)` sets the shell mode `'hq-place'` and `false` clears it when it is the current mode; a click in that mode calls `ctx.onHQPlaced({ lat, lon })`.
- Produces in the manifest: `mapLayers: [HQ_LAYER]`, `mapSetup: setupHQMap`.
- Produces in `useMap.js`: the facade passes `ctx = { onHQPlaced, ... }` to `shell.install` and returns `setHQ` and `setHQPlacementMode` from the api of the manifest named `settings` (the facade may name a module: it is a legacy file until step 5; the shell does not).

- [ ] **Step 1: Write the failing tests**, each `[T427]`, with a shell on a real map: `the settings manifest contributes one layer at z-index 15` (`collectMapLayers([settings])` has the id `settings-hq`); `setHQ draws one feature and clears it for null`; `a click in placement mode reports lat and lon and nothing else handles it` (a mode-less handler registered beside it is not called); `leaving placement mode restores normal clicks`; `validateManifest(settings)` is `[]`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/modules/settings/map`. Expected: FAIL (`Failed to resolve import "./hqLayer.js"`).
- [ ] **Step 3: Move** the HQ code out of `useMap.js`; add the two manifest fields; wire the two delegating names.
- [ ] **Step 4: Run** the HQ tests of the view (`MapView.test.js` drives `onHQPlaced` and `setHQ` through the mocked facade), the facade tests and the module checks of plan 1. Run: `cd bee-with-me\frontend; npm test -- src/modules src/composables src/views src/platform src/architecture.test.js; npm run build`. Expected: PASS and a clean build.
- [ ] **Step 5: Commit** `refactor(settings): T427 the HQ marker is contributed by the settings module`.

dod:
- `cd bee-with-me\frontend; npm test -- src/modules src/composables src/views src/platform src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`
