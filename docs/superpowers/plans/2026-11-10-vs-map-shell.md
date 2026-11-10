# Vertical slices: map-shell extraction (contribution points for layers, banners, popups, context menu) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract a map shell into `frontend/src/platform/map-shell/` with four contribution points (map layers with z-order and toggle buttons, alarm banners by priority, popups on feature click, context-menu items) that modules fill, and route today's map features through those points, with no visible change.

**Architecture:** The shell owns the OpenLayers map, the z-order table, one exclusive "map mode" and the dispatch of click, pointer-move and context-menu events. It is created at component set-up without a target and mounted later, exactly as `useMap.js` builds its sources and layers at set-up and the `ol/Map` in `onMounted` today, so calls that arrive before mount keep working. `useMap.js` stays as a facade with today's signature and return value, so `MapView.vue` and the four `MapView*.test.js` files (which replace `useMap` with a mock) keep working unedited. Features that have no module yet (fire, tracking, SOS, repeaters) contribute through *legacy entries*: plain objects of the contribution shape that live next to today's code and move into the module in its own step. The first real module contribution is the HQ marker of `settings` (last task). The click and pointer behaviour that no test pins today is pinned by characterisation tests **before** the refactor.

**Tech Stack:** Vue 3 `<script setup>`, OpenLayers 10, Pinia, vitest with `@vue/test-utils`, dependency-cruiser (existing). No new dependency.

**Spec:** [`docs/superpowers/specs/2026-10-31-vertical-slices-programme-design.md`](../specs/2026-10-31-vertical-slices-programme-design.md) (section 5 "Step 2", section 7 "Exact split of `useMap.js`": the `frontend-designer` decides within modular-monolith.md section 7), `Architecture/application/modular-monolith.md` sections 3.2, 3.3 and 7, ADR 17. Template and shared rules: [`2026-11-10-vs-step1-settings.md`](2026-11-10-vs-step1-settings.md) section 1. Wave overview: [`2026-11-10-vs-wave1-overview.md`](2026-11-10-vs-wave1-overview.md).

**Base:** `upstream/develop` at `2472543`. Execution branches: `feature/vs-map-<task>` off `develop`, one PR per task.

## Global Constraints

- **All tasks of this plan are executed by the `frontend-designer` agent** (dispatched with the Agent tool); hooks deny `.vue` and `.css` edits to anyone else. Each task is one PR that is green on its own.
- No visible change: same DOM structure, classes, `data-testid` and `data-layer` attributes, texts, z-order, click precedence, cursor, tooltip and coordinate read-out in every mode, timers and keyboard behaviour. No new i18n key, no CSS change other than moving a rule with its element. The one deliberate addition is error isolation (a failing contribution is logged and skipped, Review Focus 3).
- `frontend/src/views/MapView.vue` keeps its path and file name (`AppLayout.vue` has `<KeepAlive include="MapView">`). `useMap(mapRef, positionList, trails, onCursorMGRS, onMeasure, groupsMap, onHQPlaced, showPhotos)` keeps its eight parameters and its 22 returned names, and every returned function keeps working when it is called before the map is mounted.
- Every existing test stays green and unedited: `views/MapView.test.js`, `MapView.b52.test.js`, `MapView.b66.test.js`, `MapView.fire.test.js`, `composables/useMap.b50.test.js`, `useMap.b54.test.js`, `useMap.b56.test.js`, `useMap.fire.test.js`, `useMap.photo.test.js`, `useMap.zones.test.js`, `components/AppLayout.test.js`, `FireAlarmBanner.test.js`, `FirePopup.test.js`, `SOSBanner*.test.js`, `architecture.test.js`, and the module checks of plan 1 (`src/modules/modules.test.js`). A task that needs to edit one of them stops and reports. These tests do not pin click or pointer behaviour (`git grep -nE "click|contextmenu|pointer|PlacementMode|MeasureMode" -- "frontend/src/composables/useMap.*.test.js"` prints nothing), which is why T422 starts with characterisation tests.
- The shell (`src/platform/**`) imports no module and no legacy feature file (`platform-imports-no-module`); it receives contributions as arguments.
- **No OpenLayers in a manifest.** A module's `index.js` (and everything it imports) holds plain data and lazy components only; code that imports `ol/*` lives in the module's `map/index.js`, which only `useMap.js` reaches through `src/modules/map.js`. Otherwise OpenLayers would move from the lazy map chunk into the entry bundle (the router, the navigation and the layout import the module list), and the four `MapView` test files, which mock `ol/proj` with two functions, would load real layer code.
- No backend change, no WebSocket change, no `fire_alert*` payload change, no i18n file change, no dependency change. `frontend/src/architecture.allowlist.json` stays empty.
- Tags: vitest `it('... [T42x]', ...)`. Commits: `refactor(map): T42x summary`, body ends with the Co-Authored-By line of the session.

## Review Focus

1. Alarm order: the SOS banner is rendered above the fire banner whatever the order of the module list, and no other banner can be placed above SOS (BP-02). Pinned by priority numbers and a check, not by array position (T420, T421).
2. Click precedence on the map: release of a long press is swallowed, then HQ placement, repeater placement, measuring, tracker hit, fire hit, bare map. A dispatcher that lets two handlers act on one click would place HQ and open a popup at once (T422, pinned before the change).
3. A contribution that throws while it is installed, while it handles an event, or (a banner) while it renders must not take the map or the SOS banner down: it is logged by id and the others go on (BP-01, BP-02, BP-03) (T421, T422).
4. Calls before mount and after unmount: `setHotspots`, `setBurntAreas`, `setZones`, `setHQ`, `setRepeaters` are called from `immediate` watchers before the map exists (`MapView.vue` lines 738 to 742, 759, 841) and must draw and return what they return today; `map()` can be `null` (as in `MapView.test.js`); overlays and document listeners are removed on unmount (T422, T423, T424, T425, T427).
5. Layer toggles remembered from the last session show again after a reload, and the zones button stays admin-only (T426).

---

## 1. Contribution contract (what step 2 and later steps build on)

Two places per module, so that the manifest stays light:

**Manifest** (`src/modules/<name>/index.js`, validated by `src/platform/manifest.js`; plain data and lazy components):

| Field | Item shape | Read by |
|-------|------------|---------|
| `mapLayers` | `{ id, zIndex, toggle?: { labelKey, order, adminOnly? } }` (a declaration: no code) | the shell takes `zIndex` from it; `MapView` renders one button per `toggle`, sorted by `order` |
| `banners` | `{ id, priority, component }` (lower priority is shown first; only the id `sos` may have a priority of 10 or less) | `BannerStack.vue` in `AppLayout` |
| `popups` (optional) | `{ id, component, kinds: string[] }` | `MapPopupHost.vue` renders the component whose `kinds` contain the selection's `kind` |
| `contextMenu` (optional) | `{ id, order, labelKey, testId?, onSelect: ({ lonLat, coordinate }) => void }` | `MapContextMenu.vue` |

**Map entry** (`src/modules/<name>/map/index.js`, may import `ol/*`; default export, listed in `src/modules/map.js` as `MAP_MODULES`, one line per module that draws on the map):

```js
export default {
  name: 'settings',                         // the module name
  layers: { 'settings-hq': (ctx) => olLayer },   // one factory per declared mapLayers id
  setup: (shell, ctx) => ({ api, dispose }),     // optional: handlers, timers, the module's own functions
}
```

`shell.install(mapEntry, declarations, ctx)` creates each declared layer with its factory and `zIndex`, then calls `setup`. Factories and `setup` run at component set-up, before the map exists: they build sources and layers and register handlers; anything that needs the `ol/Map` itself (hit tests, timers) is read at event time through `shell.map` or started in `shell.onMounted(fn)`.

A **legacy entry** has exactly the shape of one item above plus a comment `// until step N`. It is defined beside the code it wraps and handed to the same collector or to `shell.install`. Moving a feature into its module means moving the entry into the module's files and deleting it from the legacy list; nothing in the shell changes.

Z-order table (today's values from `useMap.js`, kept in one place, `src/platform/map-shell/zorder.js`): weather 2, burnt areas 3, suppression zones 3.4, hotspots 3.5, graticule 4, trail 5, checkpoints 6, trackers 10, repeaters 14, HQ 15, measure 20.

Priorities: SOS banner 10, fire alarm banner 20.

### How fire attaches in step 2 (prepared here, not done here)

| Fire piece today | After this plan | Step 2 does |
|------------------|-----------------|-------------|
| three layers, styles, hit test, 60 s repaint timer in `useMap.js` | `src/composables/map/fireLayerList.js` (declarations with toggles, no `ol`) and `src/composables/map/fireLayers.js` (the map entry `LEGACY_FIRE_MAP`) (T423) | `git mv` them to `src/modules/fire/map/layers.js` and `map/index.js`, list the declarations in the fire manifest and the entry in `src/modules/map.js`, delete the legacy install line in `useMap.js` |
| `FireAlarmBanner` in `AppLayout` | legacy banner entry, priority 20 (T421) | move the entry to the fire manifest `banners` |
| `FirePopup` and its overlay in `MapView` | legacy popup entry rendered by `MapPopupHost` (T424) | move the popup logic of `MapView.vue` (lines 491 to 616) into a fire container component and contribute it |
| "Report fire here" | legacy context-menu entry (T425) | move the entry to the fire manifest `contextMenu` |
| three toggle buttons | `toggle` on the three declarations (T423, T426) | nothing more |

The fire pill, the attribution line, the focus ring and the two fire dialogs stay in `MapView.vue` in this wave; step 2 owns them.

## 2. File map and who else touches each file (as of `2472543`)

Commands used: `git grep -nE "(from|import\() *'[^']*(composables/useMap|/useMap|nav-config|AppLayout|SOSBanner|FireAlarmBanner)" -- frontend/src`, `git grep -n "vi.mock(" -- "frontend/src/views/MapView*.test.js"`, `git diff --name-only upstream/develop...<branch>` for every unmerged branch.

| File | This plan | Also read or written by |
|------|-----------|-------------------------|
| `frontend/src/views/MapView.vue` (hot, 1580 lines) | T424, T425, T426 (one after the other) | plans 1 and 3 do not touch it; `main` holds B66 and B67 edits that `develop` lacks (owner's reconcile); four test files mount it with `useMap` mocked |
| `frontend/src/composables/useMap.js` (hot, 1108 lines) | T422, T423, T427 (one after the other) | plan 1 leaves a re-export at `composables/useSettings.js` so line 23 keeps working; plan 3 leaves one at `lib/groups.js` (line 24); six `useMap.*.test.js` files call the real composable |
| `frontend/src/components/AppLayout.vue` | T421 | plan 1 changes `nav-config.js`, which it imports, not the file itself; `AppLayout.test.js` stubs `SOSBanner` and `FireAlarmBanner` by name |
| `frontend/src/platform/manifest.js` | T420 (optional fields) | `architecture.test.js` (T306 test of the required fields); plan 1's `platform/registry.js` calls `validateManifest` |
| `frontend/src/modules/index.js` | read by T421, T424, T425, T426; not edited | created by plan 1 (T403); edited by T404 and plan 3 |
| new: `frontend/src/modules/map.js` | T422 creates it empty (`MAP_MODULES = []`); T427 adds `settings` | step 2 and later steps add one line each; only `useMap.js` imports it |
| `frontend/src/modules/settings/index.js` | T427 adds the `mapLayers` declaration | created by plan 1 (T404) |
| new: `frontend/src/platform/map-shell/{contributions,zorder,createMapShell}.js`, `BannerStack.vue`, `MapPopupHost.vue`, `MapContextMenu.vue`, tests next to them | T420 to T425 | step 2 and later steps read them |
| new: `frontend/src/components/legacyBanners.js`, `frontend/src/composables/map/{fireLayerList,fireLayers}.js`, `frontend/src/modules/settings/map/{layers,index}.js`, `frontend/src/composables/useMap.interaction.test.js` | T421, T423, T427, T422 | step 2 moves the fire files |

Not touched: `i18n/en.js`, `bg.js`, `router/index.js`, `nav-config.js`, `stores/*`, `api/*`, `style.css`, every backend file, `importlinter.toml`, `allowlist.json`, `main.py`.

## 3. Task order, PRs, reviewers, parallel work

| PR | Task | Content | Needs | Reviewers |
|----|------|---------|-------|-----------|
| 1 | T420 | contribution collectors, z-order table, optional manifest fields | nothing | breaker |
| 2 | T421 | banner point in `AppLayout` | T420, T403 | breaker |
| 3 | T422 | characterisation tests, then the shell core under the `useMap` facade | T420, T403 | breaker |
| 4 | T423 | fire layers as a contribution | T422 | breaker |
| 5 | T424 | popup point in `MapView` | T420, T403 | breaker |
| 6 | T425 | context-menu point in `MapView` | T424 | breaker |
| 7 | T426 | layer toggle buttons from contributions | T425, T423 | breaker |
| 8 | T427 | HQ marker as the `settings` module's layer | T423, T404 | breaker |

T403 (plan 1) creates `src/modules/index.js`; every task from T421 on imports from `src/modules/`.

No file of this plan is on the security-critical list (`src/api/**`, `src/router/**`, `stores/auth.js`, `package.json`, `vite.config.js`), so the `security-reviewer` is not required; if a task turns out to need one of those files it stops and reports.

**Inside the plan.** T420 first. Then two chains that never share a file and run in parallel: chain U (`useMap.js`): T422, T423, T427; chain V (`MapView.vue`): T424, T425, T426. T421 (`AppLayout.vue`) is parallel to both. T426 is the one join: it reads the toggle declarations T423 creates, so it starts after T423 is merged. Never run two tasks of one chain at the same time: `MapView.vue` and `useMap.js` are single large files and a parallel edit of either is a hand merge of a 1500-line file.

**Against the other two plans.** Plan 1 and plan 3 edit neither `MapView.vue`, `useMap.js` nor `AppLayout.vue`. The only shared file is `src/modules/settings/index.js` (T404 creates it, T427 adds one field): T427 runs after T404, no conflict. Plan 1's test `a file that re-exports from src/modules is only a re-export` checks only files that contain `export * from '../modules/`; `useMap.js` imports `../modules/map.js` without re-exporting and is not a shim. If the owner merges `main` into `develop` (B66, B67 in `MapView.vue`) while a chain V task is open, merge `upstream/develop` into the branch and rerun the four `MapView*.test.js` files; do not rebase.

**PR gate (every PR), in this order:** (1) the task's DoD; (2) `cd bee-with-me\frontend; npm test; npm run build`, and the build output shows no `ol` module in the entry chunk that was not there before (compare the entry chunk size with the base; state both numbers in the PR body); (3) `python tools/smoke.py` (step f builds the frontend image and serves the SPA), PASS lines in the PR body; (4) a manual look at the map in the dev stack by the maintainer for the element the task moved (banner order, popup position, context menu, toggle buttons, HQ marker, the coordinate read-out while measuring), listed as a checkbox in the PR body, and a reminder to run the impeccable detector; (5) `breaker` on the head commit until `VERDICT: PASS`; (6) `gh pr create` is run by the human with `--body-file`.

## 4. Risks, rollback, not verified

| Risk | Mitigation |
|------|------------|
| The tests mock `useMap` entirely, so `MapView` tests cannot see a facade mistake, and no existing test pins clicks, modes, long press or the context menu | T422 step 1 writes `useMap.interaction.test.js` against the unchanged facade, green before the refactor and unedited through it; the manual check of the PR gate covers the seam |
| One exclusive map mode replaces three booleans (`hqPlacementMode`, `repeaterPlacementMode`, `measureMode`) | the characterisation tests include "HQ and measure requested together": if today's result cannot be reproduced with one mode, the three booleans stay inside the facade and only the dispatch moves to the shell; say which in the PR body |
| A facade function is called before mount | the shell and every install exist from set-up; T422, T423 and T427 each test "called before mount, then mounted" |
| `vi.mock('ol/Overlay')` and `vi.mock('ol/proj')` apply to every importer in the four `MapView` test files | `MapView.vue` and the manifests import no layer code (Global Constraints); the new `.vue` hosts import only `ol/Overlay` and `ol/proj`, as `MapView.vue` does today |
| A banner rendered through `<component :is>` is not stubbed by name in `AppLayout.test.js` | T421 step 4 runs that test first; fallback: `BannerStack` renders the legacy entries through named components and the dynamic path only for manifest entries |
| `KeepAlive` loses the map when the component name changes | `MapView.vue` is not renamed or wrapped |
| Performance: more indirection per pointer move | handlers are plain function calls in a short array; no reactive state is added on the pointer path |
| bee-dev shows a broken map | smoke builds the image but opens no browser: the manual check in the PR gate is mandatory for this plan |

**Rollback.** Frontend only, no data: `git revert -m 1 <merge commit>`, newest first inside a chain (T427, T423, T422 and T426, T425, T424); T421 alone; T420 last.

**Not verified while planning (the executor checks it in the named step):**
- That `@vue/test-utils` stubs a component by name when it is rendered through `<component :is>` inside a child component (T421 step 4).
- That real `click` and `pointermove` events can be dispatched on an `ol/Map` in jsdom well enough for the characterisation tests (T422 step 1: `map.dispatchEvent` with a `pixel` and a `coordinate`, and `forEachFeatureAtPixel` replaced by a spy where jsdom cannot render). If a behaviour cannot be exercised in jsdom, it is listed in the PR body and covered by the manual check.
- The exact markup the `MapView` tests query for the popup anchor and the context menu beyond `data-testid="report-fire-here"`, `.map-context`, `.mc-item`, `.fire-popup-anchor` (T424, T425 step 1: read the four test files before moving markup).
- No browser was opened while planning.

## 5. Existing tests

Listed in Global Constraints; none is edited, not even for import paths (no tested file moves in this plan). New tests sit next to the new files.

## 6. Open to the owner and hand-offs

1. **Scope of the shell in this wave.** Tracker markers, trails, checkpoints, repeaters, the graticule, measuring, the weather layer and the basemaps stay inside the `useMap` facade and are only registered through the shell (z-order, events). They move out with `tracking` (step 3), `devices` (step 4), `weather` and `maps` (step 5). Confirm, or ask for the tracker layers now (one more task in chain U).
2. **The tracker side panel** (modular-monolith.md section 7, "side panels") is not made a contribution point here; it is `tracking`'s (step 3).
3. **The `offline-map-changed` window event** in `MapView.vue` stays; the spec moves it into a `maps` contribution in step 5.
4. **To the architecture owner (text proposal, not edited here):** modular-monolith.md section 7 gets the contract of section 1 (manifest declarations and the separate map entry, `popups`, `contextMenu`, `toggle`), the z-order table, the banner priorities and the rule that only SOS may sit at priority 10 or less.
5. **Banner priorities** 10 (SOS) and 20 (fire) leave room between them; a future generic field signal (FX-04) needs a number from the owner.
6. **Error isolation is new behaviour** (a failing banner or map contribution is skipped and logged instead of breaking the page). It is the only deliberate difference; if the owner wants literally none, drop the `onErrorCaptured` part of T421 and the try/catch of T422.

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
- Produces in `contributions.js` (pure, imports only `./zorder.js`; each function takes `(modules, legacy = [])`, where `modules` are manifests and `legacy` are items of the same shape):
  - `collectBanners(modules, legacy) -> item[]` sorted by `priority`, then `id`.
  - `collectMapLayers(modules, legacy) -> item[]` sorted by `zIndex`, then `id`.
  - `collectLayerToggles(modules, legacy) -> { id, labelKey, order, adminOnly }[]`: one per layer item that has `toggle`, sorted by `order`.
  - `collectPopups(modules, legacy) -> item[]`; `popupFor(popups, kind) -> item | null` (the first whose `kinds` contain `kind`).
  - `collectContextMenu(modules, legacy) -> item[]` sorted by `order`, then `id`.
  - `contributionProblems(modules, legacy) -> string[]`: an `id` used twice within one kind; two banners with the same `priority`; a banner other than `sos` whose `priority` is not greater than `BANNER_PRIORITY.sos`; a popup `kind` claimed twice.
- Produces in `manifest.js`: `validateManifest` also checks, only when the field is present: `popups` is an array of `{ id: text, component, kinds: non-empty array of text }`; `contextMenu` is an array of `{ id: text, order: finite number, labelKey: text, onSelect: function }`; a `mapLayers` item's `toggle` is `{ labelKey: text, order: finite number }`; a `mapLayers` item has no `create` and the manifest has no `mapSetup` (message: `map code belongs in map/index.js, not in the manifest`).

- [ ] **Step 1: Write the failing tests**, each `[T420]`: `banners come out by priority whatever the list order` (modules `[fire(20), sos(10)]` and the reverse both give `['sos', 'fire']`); `legacy entries and manifest entries are merged` (one of each kind); `map layers come out by zIndex` (3.5, 3, 3.4 gives 3, 3.4, 3.5); `layer toggles come out by order and carry adminOnly`; `popupFor picks by kind and returns null for an unknown kind`; `context menu items come out by order`; `contributionProblems names a duplicate id, a duplicate banner priority, a kind claimed twice and a banner placed above SOS` (a banner `x` with priority 5 and one with priority 10 each give a problem naming `x`; `sos` at 10 gives none); `validateManifest accepts the optional fields and names each malformed one` (a complete manifest with `popups`, `contextMenu` and a layer with `toggle` gives `[]`; a popup without `kinds`, a menu item without `onSelect`, a toggle without `order`, a layer with `create`, a manifest with `mapSetup` each give a message containing the field name); `Z and BANNER_PRIORITY hold today's values` (the two literals above).
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
- Consumes: `collectBanners`, `contributionProblems`, `BANNER_PRIORITY` (T420); `MODULES` from `src/modules/index.js` (plan 1, T403).
- Produces: `BannerStack.vue` with one prop `banners` (array of `{ id, priority, component }`, already sorted); it renders each `component` in order with `:key="id"` and adds no element of its own, so the DOM under `<main class="main-content">` is what it is today. Each banner is rendered inside its own renderless boundary: an error thrown while that banner renders or updates is caught (`onErrorCaptured` returning `false`), logged as `console.error('banner <id> failed', error)`, and that banner alone renders nothing; the banners before and after it stay.
- Produces in `legacyBanners.js`: `export const LEGACY_BANNERS = [{ id: 'sos', priority: BANNER_PRIORITY.sos, component: SOSBanner }, { id: 'fire-alarm', priority: BANNER_PRIORITY.fireAlarm, component: FireAlarmBanner }]`, with the comments `// until step 3` and `// until step 2`.
- Produces in `AppLayout.vue`: `<BannerStack :banners="banners" />` in place of `<SOSBanner />` and `<FireAlarmBanner />`, with `const banners = collectBanners(MODULES, LEGACY_BANNERS)`. Everything else in the file is unchanged (the `useFireStore` use in `onMounted` stays).

- [ ] **Step 1: Write the failing tests**, each `[T421]`: `renders banners in the given order without a wrapper` (two stub components with root classes `a` and `b`; the mounted stack's HTML has `a` before `b` and the stack adds no element of its own); `the legacy list puts SOS above fire and has no problem` (`collectBanners([], LEGACY_BANNERS).map(b => b.id)` equals `['sos', 'fire-alarm']`; `contributionProblems(MODULES, LEGACY_BANNERS)` has no banner problem); `a module banner with priority 15 lands between them` (a fixture manifest; ids `['sos', 'x', 'fire-alarm']`); `a banner that throws while rendering is skipped and logged, and SOS stays` (banners `sos` (stub), `x` (its render function throws), `fire-alarm` (stub); both stubs are in the HTML and `console.error` was called with a message containing `x`); `the layout shows SOS above the fire alarm` (mount `AppLayout` as `AppLayout.test.js` does, with `SOSBanner` and `FireAlarmBanner` stubbed by name; inside `.main-content` the SOS stub element comes before the fire stub element).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/platform/map-shell/BannerStack.test.js`. Expected: FAIL (`Failed to resolve import "./BannerStack.vue"`).
- [ ] **Step 3: Implement** the stack, the legacy list and the `AppLayout.vue` edit.
- [ ] **Step 4: Run** the unedited layout and banner tests first, then the new ones and the module checks. Run: `cd bee-with-me\frontend; npm test -- src/components src/platform src/modules; npm run build`. Expected: PASS and a clean build. If the name stubs of `AppLayout.test.js` do not apply through `<component :is>`, use the fallback of section 4 and say so in the PR body.
- [ ] **Step 5: Commit** `refactor(map): T421 alarm banners come from contributions, ordered by priority`.

dod:
- `cd bee-with-me\frontend; npm test -- src/components src/platform src/modules`
- `cd bee-with-me\frontend; npm run build`

### Task 422: pin the map interaction, then put the shell core under the `useMap` facade

**risk:** normal
**owner:** frontend-designer
**Files:**
- Create: `frontend/src/composables/useMap.interaction.test.js` (first commit, against the unchanged `useMap.js`)
- Create: `frontend/src/platform/map-shell/createMapShell.js`, `frontend/src/modules/map.js`
- Modify: `frontend/src/composables/useMap.js` (map construction, the two `click` handlers, the two `pointermove` handlers, the context-menu and long-press wiring, the three mode booleans, the `zIndex` literals)
- Test: `frontend/src/platform/map-shell/createMapShell.test.js`

**Interfaces:**
- Consumes: `Z` (T420); `createLongPress` from `src/lib/longPress.js` (passed in by the facade: the shell does not import `src/lib`); `src/modules/` exists (T403).
- Produces in `src/modules/map.js`: `export const MAP_MODULES = []` (one map entry per line, alphabetical; only `useMap.js` imports this file).
- Produces `createMapShell({ view, controls, overlays, longPress }) -> shell` (plain JavaScript, no Vue import). It is created at component set-up; it builds no `ol/Map` until `mount`:
  - `shell.addLayer({ id, zIndex, layer })`: sets the z-index on the layer and keeps it (adds it to the map at once when already mounted); a second layer with the same `id` throws `Error('map layer <id> is already registered')`. `shell.layer(id)` returns it or `undefined`.
  - `shell.install(mapEntry, declarations, ctx) -> api`: for each declaration whose `id` has a factory in `mapEntry.layers`, `addLayer({ id, zIndex, layer: factory(ctx) })`; then `mapEntry.setup?.(shell, ctx)`; returns the `api` of the setup or `{}`; keeps `dispose` for `shell.dispose()`. An exception from a factory or from `setup` is caught, logged as `console.error('map contribution <name> failed to install', error)` and the install of the others goes on; `install` then returns `{}`.
  - `shell.mount(target)`: builds the `ol/Map` with the registered layers, the view, the controls and the overlays, attaches the event dispatch and the viewport listeners, then calls the `shell.onMounted(fn)` callbacks in registration order. `shell.map` is `null` before `mount` and after `dispose`.
  - `shell.setMode(name | null)`, `shell.mode()`: one exclusive mode.
  - `shell.onClick(handler, { mode, order = 100 })` and `shell.onPointerMove(handler, { mode, order = 100, always = false })` return an unsubscribe function and may be called before `mount`. On a click: if the long press reports `shouldSwallowClick()`, the click goes to nobody; otherwise the handlers registered for the current mode run, or, when the mode is `null`, the handlers without a mode run in `order`; a handler that returns `true` stops the ones after it. On a pointer move that is not a drag: handlers with `always: true` run in every mode, the others follow the click rule. A handler that throws is logged and skipped.
  - `shell.onContextMenu(handler)`: called with `{ coordinate, pixel }` for a right click or a long press, once per gesture: a second report within 800 ms is dropped, and the time of a report is recorded before the mode is looked at, as today (`useMap.js` lines 891 to 895); the handler is not called while a mode is active.
  - `shell.dispose()`: disposes contributions, removes the viewport listeners, calls `map.setTarget(null)`.
- Produces in `useMap.js`: the same eight parameters and 22 returned names. The shell is created in the body of `useMap()` (set-up), the facade's own layers are registered there through `shell.addLayer` with values of `Z`, and `shell.mount(mapRef.value)` replaces `new Map(...)` in `onMounted`; `map: () => shell.map`. `setHQPlacementMode(on)`, `setRepeaterPlacementMode(on)` and `setMeasureMode(on)` set the modes `'hq-place'`, `'repeater-place'`, `'measure'` (switching one off clears the mode only when it is the current one). The tooltip and coordinate read-out handler (today lines 763 to 793) is registered with `always: true`; the fire cursor handler without it. The tracker click handler is mode-less with `order` 10 and, as today, runs only when a fire click callback is registered and calls it with `null` before it reports the tracker; the fire and bare-map handler has `order` 20. The callbacks given to `onTrackerClick`, `onMapContextMenu`, `onFireFeatureClick` and `onRepeaterPlaced` are kept in facade variables as today, so they may be set before mount. After its own layers the facade calls `shell.install(entry, declarationsOf(entry.name), ctx)` for every entry of `MAP_MODULES` (none yet), where the declarations are the `mapLayers` of the manifest with that name.

- [ ] **Step 1: Pin today's behaviour.** Write `useMap.interaction.test.js` against the **unchanged** `useMap.js`, each `[T422]`, with the set-up of `useMap.fire.test.js` (a throwaway component, the `ResizeObserver` shim) and events sent with `api.map().dispatchEvent({ type: 'click', pixel, coordinate, originalEvent: {} })`; where jsdom cannot hit-test, `api.map().forEachFeatureAtPixel` and `hasFeatureAtPixel` are replaced by spies that report a chosen layer's feature: `a click in HQ placement mode reports lat and lon and nothing else, even over a tracker`; `repeater placement reports to onRepeaterPlaced`; `HQ placement wins when HQ and repeater placement are both on`; `measure mode adds A, then B and reports distance and bearing, and a third click starts again`; `a tracker hit calls the fire callback with null, then the tracker callback with the id`; `a tracker click does nothing when no fire callback is registered`; `a hotspot hit reports kind, properties and the feature coordinate`; `a bare click calls both callbacks with null`; `no tracker or fire callback runs in a placement or measure mode`; `the click after a long press reaches nobody`; `the coordinate read-out callback runs on a pointer move in every mode` (normal, HQ placement, measure); `a right click reports coordinate and pixel once, a second within 800 ms is dropped, and none is reported in a mode`; `setHotspots, setZones and setHQ called before mount draw after mount` (call them in set-up, then mount: the features are on their layers; `setHotspots` returned `true`). Run: `cd bee-with-me\frontend; npm test -- src/composables/useMap.interaction.test.js`. Expected: PASS on the unchanged code. Commit `test(map): T422 pin map clicks, modes, long press and the context menu`. A behaviour that cannot be exercised in jsdom is listed in the PR body.
- [ ] **Step 2: Write the failing shell tests** in `createMapShell.test.js`, each `[T422]`: `layers registered before mount are on the map after mount with their z-index, and a duplicate id throws`; `install runs the factories of the declared layers and the setup, and returns its api, before mount`; `a contribution that throws in a factory or in setup is logged and the next one is still installed`; `mode handlers win over mode-less ones`; `mode-less click handlers run in order and stop at the first that returns true` (orders 20 and 10 registered in that sequence; the order-10 handler returns `true`; the order-20 handler is not called); `an always pointer handler runs in every mode and a plain one only without a mode`; `a click after a long press reaches no handler`; `a throwing click handler is logged and the next one runs`; `the context menu is reported once per gesture, not while a mode is active, and a report in a mode still starts the 800 ms window`; `onMounted callbacks run at mount and dispose removes the target and calls every dispose`. Run: `cd bee-with-me\frontend; npm test -- src/platform/map-shell/createMapShell.test.js`. Expected: FAIL (`Failed to resolve import "./createMapShell.js"`).
- [ ] **Step 3: Implement the shell, then switch the facade to it** in this order, running `src/composables` after each: shell creation at set-up, `addLayer` and `mount`; modes; click and pointer-move dispatch; context menu and long press; unmount through `shell.dispose()`. `useMap.interaction.test.js` is not edited.
- [ ] **Step 4: Run** the shell tests, the interaction tests, the six unedited `useMap` test files, the four `MapView` test files, the module checks and the architecture test. Run: `cd bee-with-me\frontend; npm test -- src/platform src/composables src/views src/modules src/architecture.test.js; npm run build`. Expected: PASS and a clean build.
- [ ] **Step 5: Commit** `refactor(map): T422 the map shell owns the map, the z-order, the mode and event dispatch`.

dod:
- `cd bee-with-me\frontend; npm test -- src/platform src/composables src/views src/modules src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`

### Task 423: fire layers as a contribution

**risk:** normal
**owner:** frontend-designer
**Files:**
- Create: `frontend/src/composables/map/fireLayerList.js` (plain data, no `ol` import), `frontend/src/composables/map/fireLayers.js`
- Modify: `frontend/src/composables/useMap.js` (the fire styles, sources, layers, hit test, repaint timer and the six fire functions leave the file; one install line and six delegating names stay)
- Test: `frontend/src/composables/map/fireLayers.test.js`

**Interfaces:**
- Consumes: `shell.install`, `shell.onClick`, `shell.onPointerMove`, `shell.onMounted`, `shell.map` (T422); `Z` (T420); `lib/fireStyle.js`, `lib/color.js` (unchanged).
- Produces in `fireLayerList.js`: `export const FIRE_MAP_LAYERS = [{ id: 'fire-burnt', zIndex: Z.burnt, toggle: { labelKey: 'fire.layers.burnt', order: 10 } }, { id: 'fire-zones', zIndex: Z.zones, toggle: { labelKey: 'fire.layers.zones', order: 30, adminOnly: true } }, { id: 'fire-hotspots', zIndex: Z.hotspots, toggle: { labelKey: 'fire.layers.hotspots', order: 20 } }]` (the button order burnt, hotspots, zones and the label keys are today's `FIRE_LAYER_BUTTONS` of `MapView.vue` line 489), with the comment `// until step 2`. It imports only `platform/map-shell/zorder.js`.
- Produces in `fireLayers.js`: `export const LEGACY_FIRE_MAP = { name: 'fire', layers: { 'fire-burnt': ..., 'fire-zones': ..., 'fire-hotspots': ... }, setup: setupFireMap }` (`// until step 2`), where `setupFireMap(shell, ctx)` returns `{ api: { setBurntAreas, setHotspots, setZones, setFireLayerVisible, setFireLabels, onFireFeatureClick }, dispose }` with the behaviour of today's functions of the same names: all six work before mount; `setHotspots` and `setBurntAreas` return `true` for readable GeoJSON and `false` for unreadable GeoJSON, keeping the previous features; layers start hidden; hotspots repaint every 60 s while visible (the timer starts in `shell.onMounted`); the fire click handler is mode-less with `order` 20 and reports `{ kind, properties, coordinate }` or `null`; `ctx.trackerHit(pixel)` lets a tracker win, for the click and for the cursor.
- Produces in `useMap.js`: `const fire = shell.install(LEGACY_FIRE_MAP, FIRE_MAP_LAYERS, ctx)` in set-up, and the six returned names are the functions of `fire`.

- [ ] **Step 1: Write the failing tests**, each `[T423]`, with a shell as in T422: `the three fire layers are registered with z-index 3, 3.4 and 3.5 and start hidden`; `setHotspots before mount returns true and the features are on the layer after mount`; `setHotspots keeps the previous features and returns false for unreadable GeoJSON` (`setHotspots({ type: 'FeatureCollection', features: 1 })`); `setFireLayerVisible shows one layer by name` (names `burnt`, `hotspots`, `zones`); `the layer list carries the toggle of each button and imports no OpenLayers` (`collectLayerToggles([], FIRE_MAP_LAYERS)` gives the ids `fire-burnt`, `fire-hotspots`, `fire-zones` in that order and only `fire-zones` is `adminOnly`; the text of `fireLayerList.js` contains no `from 'ol`); `dispose stops the repaint timer` (fake timers: after `dispose()` advancing 60 s calls `changed()` on no layer).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/composables/map/fireLayers.test.js`. Expected: FAIL (`Failed to resolve import "./fireLayers.js"`).
- [ ] **Step 3: Move** the fire code out of `useMap.js` into the new files without changing a style value, a hit tolerance (6 px for hotspots) or a message; wire the install line and the six names.
- [ ] **Step 4: Run** the new tests, the unedited interaction, fire and zone tests of the facade, and the rest. Run: `cd bee-with-me\frontend; npm test -- src/composables src/platform src/views src/modules src/architecture.test.js; npm run build`. Expected: PASS and a clean build.
- [ ] **Step 5: Commit** `refactor(map): T423 fire layers are one contribution, ready to move in step 2`.

dod:
- `cd bee-with-me\frontend; npm test -- src/composables src/platform src/views src/modules src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`

### Task 424: popup point in the map view

**risk:** normal
**owner:** frontend-designer
**Files:**
- Create: `frontend/src/platform/map-shell/MapPopupHost.vue`
- Modify: `frontend/src/views/MapView.vue` (the `fire-popup-anchor` block of the template; the `fireOverlay` and `fireMap` variables; the overlay creation in the first `onMounted` (lines 710 to 718); `fireOverlay.setPosition(...)` in the `onFireFeatureClick` callback (line 727) and in `closeFirePopup` (line 525); the removal in `onUnmounted` (lines 859 to 864))
- Test: `frontend/src/platform/map-shell/MapPopupHost.test.js`

**Interfaces:**
- Consumes: `collectPopups`, `popupFor` (T420); `MODULES` (T403); `map()` and `onFireFeatureClick` of the `useMap` facade (unchanged names).
- Produces `MapPopupHost.vue`: props `map` (an `ol/Map` or `null`), `popups` (collected list), `selection` (`{ kind, coordinate, ... } | null`), `anchorClass` (string). It owns one `ol/Overlay` (`positioning: 'bottom-center'`, `offset: [0, -16]`, `stopEvent: true`, `autoPan` with a 200 ms animation and a 24 px margin, 0 ms when `prefers-reduced-motion: reduce` matches) on an element with `anchorClass`; it renders the default slot inside that element, passing `{ popup, selection }` (`popup` is `popupFor(popups, selection.kind)`); after the content is rendered (`nextTick`) it sets the overlay position to `selection.coordinate`, or to `undefined` without a selection; it removes the overlay from the map on unmount; with `map === null` it renders the anchor and does nothing else.
- Produces in `MapView.vue`: a legacy popup entry `{ id: 'fire', component: FirePopup, kinds: ['hotspot', 'burnt_area'] }` (`// until step 2`) collected with `collectPopups(MODULES, [entry])`; the host is used with `anchor-class="fire-popup-anchor"` and its slot renders the popup component with exactly today's props and listeners (`kind`, `properties`, `lon-lat`, `is-admin`, `busy`, `error-text`, `close`, `dismiss`, `extinguish`, `create-zone`). `closeFirePopup` only clears `firePopup` (the host clears the position). The focus ring keeps its own overlay in `MapView.vue`; it needs the map, so the variable that holds the map for the unmount path stays for it.

- [ ] **Step 1: Read, then write the failing tests.** Read the four `MapView*.test.js` files for every query on the popup (`.fire-popup-anchor`, the `FirePopup` stub, `addOverlay`, `removeOverlay`, `setPosition`) and keep each queried element and call. Tests, each `[T424]`, with a fake map `{ addOverlay: vi.fn(), removeOverlay: vi.fn() }` and `ol/Overlay` mocked as a class recording `setPosition` calls: `adds one overlay on mount and removes it on unmount`; `renders the slot with the popup that claims the selection kind` (popups for `a` and `b`; selection kind `b`); `positions the overlay after the content is rendered and clears it when the selection goes` (`setPosition` called with the coordinate, later with `undefined`); `an unknown kind renders nothing and clears the position`; `a null map renders the anchor and touches no overlay`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/platform/map-shell/MapPopupHost.test.js`. Expected: FAIL (`Failed to resolve import "./MapPopupHost.vue"`).
- [ ] **Step 3: Implement** the host and replace the popup block and its overlay handling in `MapView.vue`. The CSS rule of `.fire-popup-anchor` moves with the element only if it is scoped to it.
- [ ] **Step 4: Run** the four unedited `MapView` test files, the popup component test, the module checks and the new test. Run: `cd bee-with-me\frontend; npm test -- src/views src/components/FirePopup.test.js src/platform src/modules src/architecture.test.js; npm run build`. Expected: PASS and a clean build.
- [ ] **Step 5: Commit** `refactor(map): T424 popups on feature click come from contributions`.

dod:
- `cd bee-with-me\frontend; npm test -- src/views src/components/FirePopup.test.js src/platform src/modules src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`

### Task 425: context-menu point in the map view

**risk:** normal
**owner:** frontend-designer
**Files:**
- Create: `frontend/src/platform/map-shell/MapContextMenu.vue`
- Modify: `frontend/src/views/MapView.vue` (the `map-context` block of the template; `ctxMenu`, `ctxMenuEl`, `openContextMenu`, `closeContextMenu`, `onOutsidePointer`, `onMenuKey`, `reportFromMenu` in the script, lines 658 to 692; the `closeContextMenu()` call in `onUnmounted`)
- Test: `frontend/src/platform/map-shell/MapContextMenu.test.js`

**Interfaces:**
- Consumes: `collectContextMenu` (T420); `MODULES` (T403); `onMapContextMenu` of the facade (unchanged).
- Produces `MapContextMenu.vue`: prop `items` (collected list); exposed methods `open({ coordinate, pixel, bounds: { width, height } })` and `close()`; it renders, only while open and only when `items` is not empty, `<div class="map-context" role="menu">` positioned at the pixel and kept inside the bounds with today's arithmetic (`x = max(4, min(pixel[0], width - 196))`, `y = max(4, min(pixel[1], height - 52))`, the raw pixel when a bound is 0), one `<button type="button" role="menuitem" class="mc-item" :data-testid="item.testId">` per item with the text `t(item.labelKey)`; opening focuses the first button after `nextTick`; a pointer-down outside the menu or the Escape key closes it (document listeners in the capture phase, added on the first open and removed on close and on unmount); choosing an item calls `item.onSelect({ coordinate, lonLat: toLonLat(coordinate) })` and then closes the menu (today `openDialog` calls `closeContextMenu()` at line 570; every way of opening a dialog, also from the tracker row and from the popup, must keep closing the menu).
- Produces in `MapView.vue`: a legacy item `{ id: 'fire-report-here', order: 10, labelKey: 'fire.report.here', testId: 'report-fire-here', onSelect: ({ lonLat }) => openDialog({ kind: 'report', target: { latitude: lonLat[1], longitude: lonLat[0] } }) }` (`// until step 2`); `onMapContextMenu((e) => menu.value?.open({ ...e, bounds }))` with the bounds read from `mapEl` as today; `openDialog` calls `menu.value?.close()` where it called `closeContextMenu()`; the unmount path still calls `onMapContextMenu(null)`.

- [ ] **Step 1: Read, then write the failing tests.** Read `MapView.fire.test.js` and `MapView.b52.test.js` for every query on the menu (`[data-testid="report-fire-here"]`, `.map-context`, focus, Escape, the dialog that opens, the menu being gone after a choice) and keep each. Tests, each `[T425]`: `closed by default and with no items it never opens`; `open shows one menu item per contribution in order with its test id and label`; `the menu stays inside the bounds` (pixel `[500, 400]` in bounds `600 x 420` gives `left: 404px; top: 368px`; pixel `[1, 1]` gives `4px` and `4px`); `the first item is focused after opening`; `Escape and an outside pointer-down close it and remove the document listeners` (spy on `document.removeEventListener`); `choosing an item calls onSelect with the coordinate and its lon/lat and closes the menu`; `unmount while open removes the document listeners`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/platform/map-shell/MapContextMenu.test.js`. Expected: FAIL (`Failed to resolve import "./MapContextMenu.vue"`).
- [ ] **Step 3: Implement** the component and replace the block and the seven script members in `MapView.vue`. The `.map-context` and `.mc-item` CSS rules move into the component unchanged.
- [ ] **Step 4: Run** the four unedited `MapView` test files, the module checks and the new test. Run: `cd bee-with-me\frontend; npm test -- src/views src/platform src/modules src/architecture.test.js; npm run build`. Expected: PASS and a clean build.
- [ ] **Step 5: Commit** `refactor(map): T425 map context-menu items come from contributions`.

dod:
- `cd bee-with-me\frontend; npm test -- src/views src/platform src/modules src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`

### Task 426: layer toggle buttons from contributions

**risk:** normal
**owner:** frontend-designer
**Files:**
- Modify: `frontend/src/views/MapView.vue` (the `v-for="name in fireLayerButtons"` button of the template; `FIRE_LAYER_BUTTONS`, `fireLayerButtons`, `toggleFire`, `ensureLayer` and the remembered-layers loop in the first `onMounted`)
- Test: `frontend/src/views/MapView.toggles.test.js`

**Interfaces:**
- Consumes: `collectLayerToggles` (T420); `FIRE_MAP_LAYERS` from `composables/map/fireLayerList.js` (T423; plain data, so the `ol` mocks of the `MapView` tests are not involved); `MODULES` (T403); `setFireLayerVisible` of the facade; `fireStore.layers` (unchanged).
- Produces in `MapView.vue`: `const layerToggles = computed(() => collectLayerToggles(MODULES, FIRE_MAP_LAYERS).filter(t => !t.adminOnly || isAdmin.value))`; the template renders one button per toggle with today's attributes (`class="bm-btn"` plus `active`, `:aria-pressed`, `:data-layer`, the text `t(toggle.labelKey)`); a local map from the toggle id to today's layer name (`fire-burnt` to `burnt`, `fire-hotspots` to `hotspots`, `fire-zones` to `zones`, `// until step 2`) keeps `data-layer`, `fireStore.layers[name]` and `setFireLayerVisible(name, on)` exactly as they are. A toggle whose id is not in that map is not rendered in this wave (no module contributes one yet; step 2 replaces the map with a state hook of the contribution).

- [ ] **Step 1: Read, then write the tests.** Read `MapView.fire.test.js` for the queries on `[data-layer]` and on `hooks.layerVisible`. New file with the mock set-up of `MapView.fire.test.js` (copied, that file is not edited), each `[T426]`: `an admin sees burnt, hotspots, zones in that order and a viewer does not see zones` (the `data-layer` values of the rendered buttons); `a click toggles the store flag and tells the map` (`fireStore.layers.hotspots` flips and `hooks.layerVisible` ends with `['hotspots', true]`); `layers remembered from the last session are shown on mount, zones only for an admin`; `the buttons are driven by the layer list` (the test's module mock of `../composables/map/fireLayerList` returns the three entries with the orders of burnt and hotspots swapped: the rendered `data-layer` order is hotspots, burnt, zones).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/views/MapView.toggles.test.js`. Expected: FAIL (the buttons still follow the constant in `MapView.vue`, so the swapped order of the last test is not rendered; the first three tests are in a separate `describe` without the swap and pin today's behaviour).
- [ ] **Step 3: Implement** the computed list and the template change.
- [ ] **Step 4: Run** all `MapView` test files and the rest. Run: `cd bee-with-me\frontend; npm test -- src/views src/platform src/composables src/modules src/architecture.test.js; npm run build`. Expected: PASS and a clean build.
- [ ] **Step 5: Commit** `refactor(map): T426 layer toggle buttons come from the layer contributions`.

dod:
- `cd bee-with-me\frontend; npm test -- src/views src/platform src/composables src/modules src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`

### Task 427: the HQ marker is the `settings` module's map layer (first real module contribution)

**risk:** normal
**owner:** frontend-designer
**Files:**
- Create: `frontend/src/modules/settings/map/layers.js` (plain data), `frontend/src/modules/settings/map/index.js` (the map entry, imports `ol/*`)
- Modify: `frontend/src/modules/settings/index.js` (`mapLayers`), `frontend/src/modules/map.js` (one line)
- Modify: `frontend/src/composables/useMap.js` (`hqSource`, `hqLayer`, `makeHQStyle`, `setHQ`, `setHQPlacementMode` and the HQ branch of the click handling leave the file; two delegating names stay)
- Test: `frontend/src/modules/settings/map/hqLayer.test.js`

**Interfaces:**
- Consumes: `shell.install` over `MAP_MODULES` in the facade, `shell.setMode`, `shell.onClick` (T422); `Z.hq` (T420); the `settings` manifest (plan 1, T404); the facade's seventh parameter `onHQPlaced`.
- Produces in `map/layers.js`: `export const HQ_LAYER = { id: 'settings-hq', zIndex: Z.hq }` (imports only `platform/map-shell/zorder.js`).
- Produces in `map/index.js`: default export `{ name: 'settings', layers: { 'settings-hq': createHQLayer }, setup: setupHQMap }`; `setupHQMap(shell, ctx)` returns `{ api: { setHQ(loc, label), setHQPlacementMode(on) }, dispose }`: `setHQ` draws or clears the marker with today's style and default label `'ЩАБ'` and works before mount; `setHQPlacementMode(true)` sets the shell mode `'hq-place'` and `false` clears it when it is the current mode; a click in that mode calls `ctx.onHQPlaced({ lat, lon })`.
- Produces in the manifest: `mapLayers: [HQ_LAYER]` (one import of `./map/layers.js`; the manifest still imports no `ol`). In `src/modules/map.js`: `MAP_MODULES = [settingsMap]`.
- Produces in `useMap.js`: the facade passes `ctx = { onHQPlaced, trackerHit }` to `shell.install` and returns `setHQ` and `setHQPlacementMode` from the api of the entry named `settings` (the facade may name a module: it is a legacy file until step 5; the shell does not). When that install failed (the api is `{}`), the two names are no-ops that log once, so the rest of the map works (BP-03).

- [ ] **Step 1: Write the failing tests**, each `[T427]`, with a shell as in T422: `the settings manifest declares one layer at z-index 15 and imports no OpenLayers` (`collectMapLayers([settings])` has the id `settings-hq`; `validateManifest(settings)` is `[]`; the texts of `modules/settings/index.js` and `map/layers.js` contain no `from 'ol`); `every declared layer has a factory and the reverse` (for every entry of `MAP_MODULES`, the keys of `layers` equal the `mapLayers` ids of the manifest with the same name); `setHQ before mount draws one feature after mount and null clears it`; `a click in placement mode reports lat and lon and nothing else handles it` (a mode-less handler registered beside it is not called); `leaving placement mode restores normal clicks`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/modules/settings/map`. Expected: FAIL (`Failed to resolve import "./index.js"`).
- [ ] **Step 3: Move** the HQ code out of `useMap.js`; add the declaration, the entry and the `MAP_MODULES` line; wire the two delegating names.
- [ ] **Step 4: Run** the HQ tests of the view (`MapView.test.js` drives `onHQPlaced` and `setHQ` through the mocked facade), the unedited interaction tests of the facade (they pin HQ placement), the module checks of plan 1 and the rest. Run: `cd bee-with-me\frontend; npm test -- src/modules src/composables src/views src/platform src/architecture.test.js; npm run build`. Expected: PASS and a clean build; the entry chunk has not grown by OpenLayers (PR gate, item 2).
- [ ] **Step 5: Commit** `refactor(settings): T427 the HQ marker is contributed by the settings module`.

dod:
- `cd bee-with-me\frontend; npm test -- src/modules src/composables src/views src/platform src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`
