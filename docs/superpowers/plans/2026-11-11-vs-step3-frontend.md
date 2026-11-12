# Vertical slices, step 3 on the frontend: the `gateway` module and the tracker panel and layers as `tracking` contributions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the gateway status its own frontend module (`frontend/src/modules/gateway/`), and move the last tracking features out of `MapView.vue` and `useMap.js`: the tracker panel becomes a panel of the `tracking` module and the tracker, trail and checkpoint layers become its map entry. Two small tasks that wave 2 left open ride along: the fire popup and dialogs are loaded when they are needed, and the app gets one global error handler.

**Architecture:** The same contribution contract as wave 2: a manifest lists live handlers, live hooks, panels and map layers; the map view and the facade read lists and name no module. The gateway status moves first (small, it removes a line of `MapView.vue` and a field of the tracking store). The panel and the layers are the two tasks wave 2 planned as T548 and T549 and postponed; they are re-planned here with new numbers and without line numbers, because the files changed under the old text.

**Tech Stack:** Vue 3 `<script setup>`, Pinia, OpenLayers 10, vitest. No new dependency.

**Spec:** [`docs/superpowers/specs/2026-10-31-vertical-slices-programme-design.md`](../specs/2026-10-31-vertical-slices-programme-design.md) section 5 ("Step 3", frontend part); `Architecture/application/modular-monolith.md` sections 3.2, 5.1 (rule 5), 7; contribution contract: [`2026-11-10-vs-map-shell.md`](2026-11-10-vs-map-shell.md) section 1 and [`2026-11-10-vs-step2-fire.md`](2026-11-10-vs-step2-fire.md) section 1.2; the superseded task texts: [`2026-11-10-vs-step2-tracking-sos.md`](2026-11-10-vs-step2-tracking-sos.md), tasks 548 and 549. Overview: [`2026-11-11-vs-wave3-overview.md`](2026-11-11-vs-wave3-overview.md).

**Base:** `upstream/develop` at `090b9cc`. Wave 2 is closed: T545 is merged (the SOS toast is the panel `sos-toast` of the `sos` module at `map-root`, order 10; `frontend/src/components/SOSToast.vue` is gone) and T590 set the frontend `completed_step` to 2. The map chain of this plan therefore starts with T630.

## Global Constraints

- The decisions of wave 2 apply: `frontend-designer` owns every `.vue` and `.css` change; the shell contract of T422 and T423 is not changed; `lib/groups.js` stays; error isolation of contributions stays; `stores/locations.js` stays as the `useLocationsStore` facade with its present names until step 5; every UI text exists in EN and BG; no manifest reaches OpenLayers statically.
- **Hardware:** no task of this plan touches the backend; all are safe without hardware.
- **One session at a time on `MapView.vue` and `useMap.js`** (the map chain of the overview): T630, T631, T632 in that order. T633 and T634 touch neither file and run beside the chain.
- No intended difference on screen in any task, except the two named ones: the gateway status is fetched with the live channel and its tick instead of with every mount of the map (T630), and a failed tracker layer is said out loud (T632).
- Every frontend PR states the initial JavaScript before and after: the sum of the `.js` files that `dist/index.html` names (the entry and its preloads), read after `npm run build` on its base and on its head. Measured for this plan on `090b9cc`: 10 files, 357.66 kB (bytes divided by 1000; the command is in T633, which adds it as `frontend/scripts/initial-js.mjs`). The largest of them are the Vue runtime chunk, the entry chunk `index` (79.62 kB) and the `api` chunk (62.43 kB), from the same build output. T633 is the task that is expected to lower the figure; T630 to T632 and T634 report it.
- Task numbers T630 to T634. Tags: vitest `[T63x]`. Existing tests stay unedited except the edits of section 4; a `MapView*.test.js` or `useMap.*.test.js` file that would need another edit stops the task.
- After every UI task the maintainer runs the impeccable detector by hand (the hook is off).

## Review Focus

1. A marker that is filtered out while its row is visible, or the reverse (BP-01): the list the panel shows and the list the map draws are one computed value of one store (T631, `the rank filter narrows the rows and the list the map gets`).
2. A marker that never goes stale because the 60 second restyle timer did not start or was not cleared (BP-01): T632, `a position that goes stale is restyled by the timer without a new message`, `dispose stops the timer`.
3. A tracker layer that fails to install takes the people off the map without a word (BP-03): T632 shows an alert note; the SOS banner and the panel keep working.
4. The gateway pill is missing or wrong for the rest of the page because the one fetch failed or ran before a login: T630 refetches the status on every resync tick.
5. Fire's "report fire at this position" button disappears from the tracker row when the row moves: it becomes a contributed row action and a test clicks it (T631).

---

## 1. Design

### 1.1 The gateway module (T630)

| Today | After |
|-------|-------|
| `serialStatus` and `applySerialStatus` in `modules/tracking/store.js`; `serial_status` in the tracking manifest's `liveHandlers` | `modules/gateway/store.js` (`useGatewayStore`: `status`, `applyStatus(data)`, `fetchStatus()`); the handler in the gateway manifest |
| `MapView.vue` fetches the status on every mount with `getSerialStatus()` | the gateway manifest's `live: { setup: fetchStatus, onTick: fetchStatus }`: once when the live channel is first connected on the page and again with every resync tick (the tick also runs after a reconnect). `setup` runs once per page, not once per mount of the map, so the tick is what heals a status that was missed (a fetch that failed, a login after a logout in the same page). A failure is swallowed as today (the port may be unconfigured) |
| the pill (`div.serial-status` with its dot and two texts) and its CSS rules in `MapView.vue` | `modules/gateway/components/GatewayStatus.vue`, a `map` panel with the same markup, classes and texts |
| texts `map.serialConnected`, `map.serialDisconnected` in the global dictionaries | the same two keys, with the same names and words, in the module's `i18n/en.js` and `bg.js` under `map` (as the weather module keeps its `map.weather*` keys): `modules.test.js` (`no text key was lost`) compares key names with `keys.snapshot.json` and has no rename table, so the names must not change |
| `useLocationsStore()` returns `serialStatus` and `applySerialStatus` from tracking | the facade returns the gateway store's `status` under the name `serialStatus` and `applyStatus` under `applySerialStatus`: its names do not change. It imports `useGatewayStore` from `modules/gateway/index.js`, which exports it next to the manifest (rule `modules-only-through-index`) |

The manifest: `name: 'gateway'`, `routes: []`, `nav: []`, `mapLayers: []`, `banners: []`, `panels: [{ id: 'gateway-status', host: 'map', order: 20, component: GatewayStatus }]`, `liveHandlers: { serial_status }`, `live` as above, `depends: []`. The component is imported statically (a few lines, no `ol`). The word "frames" after the counter is a hard-coded English word in today's template; it moves as it is and is reported, not translated, in this task.

**Correction after the merge (follow-ups of wave 3, B141 to B148).** The host of the gateway pill (T630) and of the tracker panel (T631) is `map`, not `map-root`: `MapView.vue` renders the `map-root` host before `.map-layout`, outside it, so a panel there is not positioned against the map area. Both panels are positioned absolutely against the map (`.serial-status` top right) or sit in the map's panel column, so both are in `map`, inside `.map-layout`. The word "frames" is translated since B141 (`gateway.frames`).

### 1.2 The tracker panel (T631, was T548)

The panel is not only markup: the filtered list is also the list the map draws, and a row carries fire's "report fire at this position" button. So the move needs shared state and one more contribution point.

- `modules/tracking/ui.js`: a Pinia store `useTrackerUi` with `viewMode`, `rankFilter`, `selectedDeviceId`, `groupsMap` (set by the view, which already loads the teams), `nowTick`, `displayList`, `groupsWithLeaders` (today's computations, reading the tracking store) and `select(deviceId)`, `startTick()`, `stopTick()`, `reset()`.
- **The tick stays with the list.** Today `displayList` is sorted by urgency with `nowTick`, a ref the view advances every 10 seconds, and the view's deep watcher on `displayList` restyles the markers on each tick. The tick therefore lives in the store, not in the panel: `displayList` reads `nowTick`, `startTick()` starts the one 10 second interval (idempotent: a second call while it runs does nothing, because the view calls it after several awaits) and `stopTick()` clears it, and **the view** calls them in its mount and unmount hooks, as it starts and clears `tickTimer` today. A panel that is not mounted must not stop the order and the restyle.
- **Refs, not values.** `useMap` calls `.value` and `watch` on the list it is given, so the view passes `storeToRefs(useTrackerUi()).displayList`, never `useTrackerUi().displayList` (an unwrapped array).
- **State per visit.** Today the mode, the rank filter and the selection are local to the view and start fresh on every visit of the map. The view calls `reset()` on mount so that stays true.
- A new optional manifest field `actions`: items `{ id, target, order, labelKey, testId?, isAvailable?: (subject) => boolean, onSelect: (subject) => void }`; `collectActions(modules, target, legacy = [])` in `platform/map-shell/contributions.js`, sorted by `order`, then `id`; `validateManifest` names a malformed item. Fire contributes `{ id: 'fire-report-at-position', target: 'tracker-row', order: 10, labelKey: <the key of today's button>, testId: 'report-fire-row', onSelect: <today's reportFromRow with its 24 hour rule> }`.
- `modules/tracking/components/TrackerPanel.vue` (prop `context`): the mode toggle and the tracker `aside` with their markup, classes and test ids; the age labels read the store's `nowTick`; the row actions from `collectActions(MODULES, 'tracker-row')`. It is a panel of the tracking manifest on the host the map view's panel column uses today (read `PANEL_HOSTS` in `platform/map-shell/contributions.js`; a new host name is added only if none fits, and then to that list and its test).
- `MapView.vue` passes the `displayList` ref of the store to `useMap` where it passes its own computed list today, keeps its deep watcher on it, and its marker-click callback calls `useTrackerUi().select`.

### 1.3 The tracker layers (T632, was T549)

- `modules/tracking/map/layers.js`: `TRACKING_MAP_LAYERS` with the ids `tracking-trail`, `tracking-checkpoints`, `tracking-trackers` and the z-indices `Z.trail`, `Z.checkpoints`, `Z.trackers` of `platform/map-shell/zorder.js`.
- `modules/tracking/map/index.js`: default export `{ name: 'tracking', layers, setup: setupTrackingMap }`; `setupTrackingMap(shell, ctx)` returns `{ api: { setPositions(list), setTrails(trailMap), setGroups(groupsMap), setShowPhotos(on), setTrailVisible(on), setCheckpointNumbers(on), refreshMarkers(list), trackerHit(pixel) }, dispose }`. It owns the marker, photo, trail and checkpoint styles, the tooltip overlay and its pointer handler, the tracker click handler (today's rule and order), the photo-loaded restyle and the 60 second stale timer (started in `shell.onMounted`, cleared in `dispose`).
- `useMap.js` keeps its parameters and returned names; its watchers call the entry's api; `makeMarkerStyle` and `makePhotoMarkerStyle` stay importable from `useMap.js` as re-exports; when the tracking entry failed to install, `refreshMarkers` returns `false`.
- `MapView.vue`: when `refreshMarkers` returns `false`, a note with `role="alert"` shows the new text `map.trackerLayerFailed` (EN "The tracker layer could not be loaded. Reload the page.", BG "Слоят с тракерите не се зареди. Презаредете страницата.") where the stale-feed banner sits. The repeater layer, the measure layer, the graticule, the basemaps and the weather tile layer stay in the facade (step 5).

## 2. File map and chains

Commands used: `git grep -nE "serialStatus|applySerialStatus|serial_status|getSerialStatus|serialConnected|serialDisconnected" -- frontend/src`; `git grep -nE "tickTimer|staleTimer|displayList|rankFilter|viewMode|reportFromRow" -- frontend/src/views/MapView.vue frontend/src/composables/useMap.js`; `ls frontend/src/views/MapView*.test.js frontend/src/composables/useMap.*.test.js`.

| File | This plan | Also touched by |
|------|-----------|-----------------|
| `frontend/src/views/MapView.vue` (hot, map chain) | T630 (pill, seed call, CSS), T631 (panel block and its state), T632 (one note) | none (T545 is merged) |
| `frontend/src/composables/useMap.js` (hot, map chain) | T632 | none |
| `frontend/src/modules/index.js`, `frontend/src/i18n/en.js`, `bg.js` (assembly chain) | T630 (one line; two keys leave), T632 (one key) | none |
| `frontend/src/modules/tracking/index.js`, `store.js` | T630 (the status leaves), T631 (`panels`, `useTrackerUi`), T632 (`mapLayers`) | none |
| `frontend/src/stores/locations.js` | T630 (two names re-pointed) | none |
| `frontend/src/platform/manifest.js`, `platform/map-shell/contributions.js` | T631 (`actions`) | none |
| `frontend/src/modules/fire/index.js` | T631 (one action), T633 (the popup import) | the two edit different entries of the manifest; T631 first, T633 merges `upstream/develop` |
| `frontend/src/modules/fire/components/FireDialogs.vue`, `frontend/scripts/initial-js.mjs` | T633 | none |
| `frontend/src/main.js`, `frontend/src/platform/errors.js` | T634 | none |
| `frontend/src/modules/mapEntries.js` | T632 | none |

## 3. Task order, PRs, reviewers

| PR | Task | Content | Needs | Owner | Reviewers | Hardware |
|----|------|---------|-------|-------|-----------|----------|
| 4 | T633 | the fire popup and the two fire dialogs are loaded when they are needed | nothing (after T631 on `modules/fire/index.js`) | frontend-designer | breaker | safe |
| 1 | T630 | frontend `gateway` module: status store, live handler, pill | nothing | frontend-designer | breaker | safe |
| 2 | T631 | the tracker panel is a `tracking` panel | T630 | frontend-designer | breaker | safe |
| 3 | T632 | tracker, trail and checkpoint layers are the `tracking` map entry | T631 | frontend-designer | breaker | safe |
| 5 | T634 | one global error handler and one handler for unhandled rejections | nothing | implementer | breaker + security-reviewer (what reaches the console: B99, B108) | safe |

The plan does not depend on any backend task of wave 3 and can run from the first day, one PR after the other. Every PR: `npm test`, `npm run build`, `python tools/smoke.py` (step f, the frontend image), a manual look at the map page with test mode running (markers, trail, tooltip, panel, SOS, the gateway pill), then `breaker`; `gh pr create` by the human.

**Rollback.** `git revert -m 1 <merge>`, newest first (T632, T631, T630); T633 and T634 are independent of the chain and of each other. **Not verified while planning:** no browser was opened; that a Pinia store (`useTrackerUi`) read by both the panel and the view keeps `displayList` identical for both is T631 step 4; which panel host the tracker column needs is read in T631 step 1.

## 4. Existing tests

| File | Edit | Kind | Task |
|------|------|------|------|
| `frontend/src/composables/useWebSocket.dispatch.test.js` | the table row `['serial_status', loc, 'applySerialStatus']` points at a mock of `../modules/gateway/store.js` with the spies `applyStatus` and `fetchStatus` (the `setup` and tick hooks call `fetchStatus`; without it the hook throws inside `connect()`) | mock path | T630 |
| `frontend/src/modules/tracking/index.test.js` | a case that expects `serial_status` among the tracking handlers expects it in the gateway manifest instead (the case moves to `modules/gateway/index.test.js`); the tracking handlers are then exactly `['location_update']` | deliberate: the handler moved | T630 |
| `frontend/src/composables/useWebSocket.test.js`, `useWebSocket.b66.test.js` | they call `connect()` without an active Pinia, so the new gateway `setup` and tick hooks run for real; `runHooks` and `runSetup` (wave 2, B98) isolate errors and rejections, so they should stay green, but they would log `live handler setup failed: ...`. Each gets a mock of `../modules/gateway/store.js` next to its existing store mocks (the same spies as in `useWebSocket.dispatch.test.js`), so no console noise is accepted | mock added, no assertion changes | T630 |
| `frontend/src/views/MapView.b66.test.js` | the case whose title starts `does not stop serial status` loses its meaning with the assertions and gets a title that says what is left of it (the other calls of that case); its two assertions `expect(api.getSerialStatus).toHaveBeenCalledTimes(1)` go: the view no longer calls it, and the test mocks `useWebSocket`, so no live hook runs. The same fact is asserted in `modules/gateway/index.test.js` (`the status is fetched in setup and on every tick`) | deliberate: the call moved into a live hook | T630 |
| the i18n tests (`no text key was lost`, parity, collisions) | none: the two keys keep their names | none | T630 |

Every other `MapView*.test.js` file and every `useMap.*.test.js` file stays unedited (they mock or call the facade, whose names do not change). `modules/sos/store.test.js` runs the `setup` hooks of the real module list; `fetchStatus` catches every failure inside itself, so the gateway hook cannot reject there.

## 5. Open questions (details in the overview, section 7)

1. **To the maintainer:** T631 and T632 were optional in wave 2. Default of this plan: T630 and T631 run; T632 runs last and may be dropped without leaving anything half-moved (the layers then stay in the facade until step 5).
3. **To the maintainer:** the settings section of fire (`FireZonesSettings.vue`, in the entry chunk today because the manifest imports it statically) is the next candidate for loading on demand; T633 leaves it and reports its size from the build output (default: a follow-up, it sits in a page that has its own chunk).
2. **To the maintainer:** translate the word "frames" in the gateway pill (a new key `gateway.frames`) in T630 or leave it (default: leave, report).

---

### Task 630: the frontend `gateway` module (status store, live handler, the pill)

**risk:** normal
**owner:** frontend-designer
**hardware:** safe
**Files:**
- Create: `frontend/src/modules/gateway/{index.js, store.js, i18n/en.js, i18n/bg.js, components/GatewayStatus.vue, index.test.js, store.test.js, components/GatewayStatus.test.js}`
- Modify: `frontend/src/modules/index.js` (one line, alphabetical: after `fire`), `frontend/src/i18n/en.js`, `bg.js` (`map.serialConnected`, `map.serialDisconnected` leave the global files and are defined, under the same names, in the module's dictionaries)
- Modify: `frontend/src/modules/tracking/index.js`, `store.js` (the status and its handler leave), `frontend/src/stores/locations.js` (two names re-pointed)
- Modify: `frontend/src/views/MapView.vue` (the pill block, the seed call in the mount hook, the `.serial-*` CSS rules, the `getSerialStatus` import)
- Modify: the tests of section 4

**Interfaces:**
- Consumes: the live dispatch and its hooks (`live.setup`, `live.onTick`), the `map` panel host (not `map-root`: see the correction under the manifest), `getSerialStatus` of `src/api`.
- Produces: the store, the manifest (default export of `modules/gateway/index.js`, with the named export `useGatewayStore`) and the panel of section 1.1. `fetchStatus()` never throws and never rejects. `GatewayStatus.vue` declares the `context` prop, renders nothing while `status` is `null`, and shows the connected or the disconnected text with the port and, when connected, the frame counter, exactly as today.

- [ ] **Step 1: Read, then write the failing tests.** Read the `MapView*.test.js` files for a query on `.serial-status` or a mock of `getSerialStatus`; apart from the two assertions of `MapView.b66.test.js` (section 4) each must keep working unedited. Tests, each `[T630]`. `store.test.js`: `applyStatus replaces the status`; `fetchStatus stores the answer`; `a failed fetchStatus leaves the status and does not reject` (also for a 401); `a null answer leaves the status unchanged and does not reject` (today `applySerialStatus(null)` throws on its destructuring and the view swallows the throw, so the status stays `null`; many existing tests mock `getSerialStatus` with a `null` answer: `fetchStatus` catches the throw and stores nothing, it must not turn `null` into an empty status, which would show a disconnected pill). `index.test.js`: `the gateway manifest is valid and in the module list`; `serial_status is handled by gateway and not by tracking`; `the status is fetched in setup and on every tick` (run the collected `setup` and `onTick` hooks of the real module list with `getSerialStatus` mocked: one call per hook run); `a status missed at setup arrives with the next tick` (the first call rejects, the second resolves: the store has the status); `the two texts keep their key names` (`map.serialConnected` and `map.serialDisconnected` resolve in both languages from the merged dictionaries); `the facade still returns serialStatus and applySerialStatus` (a status applied through `useLocationsStore().applySerialStatus` is read from `useGatewayStore().status`). `GatewayStatus.test.js`: `shows connected with port and counter`; `shows disconnected with the port`; `renders nothing without a status`; `the root element carries no context attribute`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/modules/gateway`. Expected: FAIL (`Failed to resolve import "./store.js"`).
- [ ] **Step 3: Move** the state, the handler, the pill with its CSS and the two texts; write the manifest and the list line; apply the test edits of section 4.
- [ ] **Step 4: Run.** Run: `cd bee-with-me\frontend; npm test; npm run build`. Expected: PASS and a clean build; the unedited `stores/locations.test.js` and `MapView*.test.js` files pass.
- [ ] **Step 5: Commit** `refactor(gateway): T630 the gateway status is a frontend module with its own store, handler and panel`. PR body: the one behaviour difference (the status is fetched when the live channel first connects and with every resync tick, no longer on every mount of the map), the chunk size before and after.

dod:
- `cd bee-with-me\frontend; npm test`
- `cd bee-with-me\frontend; npm run build`

### Task 631: the tracker panel becomes a panel of the tracking module (was T548)

**risk:** normal
**owner:** frontend-designer
**hardware:** safe
**Files:**
- Create: `frontend/src/modules/tracking/ui.js`, `modules/tracking/components/TrackerPanel.vue`, `modules/tracking/components/TrackerPanel.test.js`, `modules/tracking/ui.test.js`, `frontend/src/views/MapView.t631.test.js`
- Modify: `frontend/src/modules/tracking/index.js` (`panels`, the named export `useTrackerUi`), `frontend/src/platform/manifest.js`, `platform/manifest.test.js`, `platform/map-shell/contributions.js`, `contributions.test.js` (`actions`), `frontend/src/modules/fire/index.js` (one action)
- Modify: `frontend/src/views/MapView.vue` (the mode toggle and the tracker `aside` in the template; in the script the state and functions named `viewMode`, `rankFilter`, `nowTick`, `tickTimer`, `rankFiltered`, `displayList`, `groupsWithLeaders`, `selectedDeviceId`, `selectDevice`, `reportFromRow`, `setViewMode`, `focusDevice`, `formatTime`, `batClass`; the panel's CSS rules)

**Interfaces:**
- Consumes: the panel hosts and the map context of wave 2, `useFireUi` of the fire module, `useTrackingStore`.
- Produces: `useTrackerUi`, the `actions` contribution point with `collectActions`, fire's `fire-report-at-position` action and `TrackerPanel.vue`, all as section 1.2 says.

- [ ] **Step 1: Read, then write the failing tests.** Read the `MapView*.test.js` files for every query on `.tracker-row`, `.tracker-panel`, `[data-testid="report-fire-row"]`, the rank filter and the mode toggle, and keep each. Read `PANEL_HOSTS`. Tests, each `[T631]`. `ui.test.js`: `displayList follows the rank filter`; `the teams view gives one leader row per team`; `select sets the selected device`; `the order of displayList changes with the tick, without a new message` (fake timers: after `startTick()` a position that became more urgent with time moves up after 10 seconds); `stopTick clears the interval`; `reset puts mode, filter and selection back`; `the displayList taken with storeToRefs is a ref a watcher can follow`. `TrackerPanel.test.js`: `rows come out by urgency and show name, MGRS, age and battery`; `the rank filter narrows the rows and the list the map gets` (the same ref is read by the panel and by a second consumer); `the age label of a row changes class when its position goes stale, without a new message` (fake timers, the store's tick); `a selected row offers the row actions of the modules and a click runs fire's action`; `the tick keeps running when the panel is unmounted` (the view owns it). In a new `views/MapView.t631.test.js` (the mock set-up of `MapView.test.js` copied): `the view starts the tick on mount, clears it on unmount and resets the tracker state on mount`; `the markers are refreshed on a tick` (`refreshMarkers` of the mocked facade is called again after 10 seconds). `contributions.test.js`: `actions are collected per target and sorted by order then id`. `manifest.test.js`: `validateManifest accepts actions and names a malformed one`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/modules/tracking src/platform`. Expected: FAIL (`Failed to resolve import "./TrackerPanel.vue"`; `collectActions is not a function`).
- [ ] **Step 3: Move** the blocks and the state; the CSS rules move with their elements.
- [ ] **Step 4: Run** the unedited `MapView*.test.js` files first, then everything. Run: `cd bee-with-me\frontend; npm test; npm run build`. Expected: PASS and a clean build. A `MapView` test that would need an edit stops the task.
- [ ] **Step 5: Commit** `refactor(tracking): T631 the tracker panel is a panel of the tracking module`.

dod:
- `cd bee-with-me\frontend; npm test`
- `cd bee-with-me\frontend; npm run build`

### Task 632: tracker, trail and checkpoint layers become the tracking map entry (was T549)

**risk:** normal
**owner:** frontend-designer
**hardware:** safe
**Files:**
- Create: `frontend/src/modules/tracking/map/layers.js`, `modules/tracking/map/index.js`, `modules/tracking/map/trackerLayers.test.js`, `frontend/src/views/MapView.trackerNote.test.js`
- Modify: `frontend/src/modules/tracking/index.js` (`mapLayers`), `frontend/src/modules/mapEntries.js`
- Modify: `frontend/src/composables/useMap.js` (the tracker, trail and checkpoint sources, layers, styles and upserts; the tooltip overlay and its handler; the tracker click handler; `staleTimer`; the watchers on the position list, the trails and the photo switch), `frontend/src/views/MapView.vue` (one note), `frontend/src/i18n/en.js`, `bg.js` (one key)

**What moves and why it is a task of its own.** It is the largest single cut of `useMap.js` and it is BP-01 directly: a marker that is not drawn, or not restyled when it goes stale, is a person the operator cannot see.

**Interfaces:**
- Consumes: `shell.install`, `shell.onMounted`, `shell.onClick`, `shell.onPointerMove` and the `ctx` of the map shell (shape unchanged); `Z.trail`, `Z.checkpoints`, `Z.trackers`; the libraries of `modules/tracking/lib/`.
- Produces: the layer list, the map entry and its api, the facade's delegation and the failure note, all as section 1.3 says; the note is pinned by `frontend/src/views/MapView.trackerNote.test.js` (new, `[T632]`: `the note is shown when refreshMarkers returns false` finds an element with `role="alert"` and the text of `map.trackerLayerFailed`; `no note when refreshMarkers returns true`); the text `map.trackerLayerFailed` in both languages.

- [ ] **Step 1: Read, then write the failing tests.** Read every `useMap.*.test.js` file; they call the real composable and are the net. Tests in `trackerLayers.test.js`, each `[T632]`, with a shell as in the map-shell tests: `the three layers are registered with the z-indices of the z-order table`; `positions set before mount are drawn after mount`; `a position that goes stale is restyled by the timer without a new message` (fake timers, 60 seconds); `dispose stops the timer and removes the tooltip overlay`; `a tracker under the pointer shows the tooltip in every mode`; `a failed install makes refreshMarkers return false` (the entry's `setup` replaced by one that throws); `a failed install leaves no timer behind` (fake timers: no pending interval after the failed `setup` and the shell's dispose). Tests in the new `src/views/MapView.trackerNote.test.js`, each `[T632]`, with `useMap` mocked as the other `MapView*.test.js` files mock it: `the note is shown when refreshMarkers returns false`; `no note when refreshMarkers returns true`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/modules/tracking/map src/views/MapView.trackerNote`. Expected: FAIL (`Failed to resolve import "./index.js"`; in the view test no element with `role="alert"`).
- [ ] **Step 3: Move** the code in this order, running `npm test -- src/composables` after each: styles; sources, layers and upserts; tooltip and click handlers; the timer and the watchers; the failure note.
- [ ] **Step 4: Run** the unedited `useMap.*.test.js` and `MapView*.test.js` files and the rest. Run: `cd bee-with-me\frontend; npm test; npm run build`. Expected: PASS and a clean build; the entry chunk did not take in OpenLayers (`no manifest reaches OpenLayers` passes).
- [ ] **Step 5: Commit** `refactor(tracking): T632 tracker, trail and checkpoint layers are the tracking module's map entry`.

dod:
- `cd bee-with-me\frontend; npm test`
- `cd bee-with-me\frontend; npm run build`

### Task 633: the fire popup and the two fire dialogs are loaded when they are needed

**risk:** normal
**owner:** frontend-designer
**hardware:** safe
**Files:**
- Create: `frontend/scripts/initial-js.mjs`, `frontend/src/modules/fire/lazy.test.js`
- Modify: `frontend/src/modules/fire/index.js` (the import of `FireMapPopup` and the `fire-dialogs` panel entry), `frontend/src/modules/fire/components/FireDialogs.vue` (the imports of `FieldReportForm` and `SuppressionZoneForm`)
- Modify: `frontend/src/modules/fire/components/FireDialogs.test.js`, `FireMapPopup.test.js`, `frontend/src/views/MapView.fire.test.js` (only an awaited flush where a test reads the popup or a dialog right after it opens)

**Why.** The fire manifest imports the popup, the dialogs panel and through it both dialog forms statically, so they are in the JavaScript every page loads first, although an operator opens a hotspot popup or a report dialog rarely. Wave 2 raised the initial JavaScript; this task takes back what is not needed at start. The alarm banner stays static on purpose (the manifest says why: the alarm must not wait for a chunk), and so do the map panel and the zones note.

**Interfaces:**
- Produces `scripts/initial-js.mjs`: run as `node scripts/initial-js.mjs` in `frontend/` after a build; it reads `dist/index.html`, takes every distinct `assets/*.js` it names (the entry and its `modulepreload` links), adds their sizes and prints `<n> files, <x> kB` (bytes divided by 1000, two decimals); exit code 1 with a message when `dist/index.html` is missing. It imports only `node:fs`.
- Produces in `fire/index.js`: `popups: [{ id: 'fire', component: defineAsyncComponent(() => import('./components/FireMapPopup.vue')), kinds: [...] }]`; the panel `fire-dialogs` keeps `FireDialogs` static and gets `retryKey: () => useFireUi().dialog`. Correction after the merge: `retryKey` does not load a failed chunk again. When `useFireUi().dialog` changes, `PanelBoundary` clears its failed flag and renders `FireDialogs` again; a form whose chunk failed is not fetched again, because `defineAsyncComponent` keeps the rejected loader promise, so the form fails at once, the boundary logs one line and hides the panel again. What `retryKey` gives is that the other dialog, and a dialog whose chunk did load, still open after one failure; the failed form needs a page reload.
- Produces in `FireDialogs.vue`: `FieldReportForm` and `SuppressionZoneForm` are `defineAsyncComponent(() => import(...))`; nothing else in the file changes (the `v-if` on `ui.dialog?.kind` already mounts each form only while its dialog is open, so each chunk is fetched at the first open). Only the report form becomes a chunk of its own: `FireZonesSettings.vue` imports `SuppressionZoneForm` statically and is itself a static panel of the manifest, so the zone form stays in the initial JavaScript until the settings section is loaded on demand (open question 3); the async import in `FireDialogs.vue` is written all the same, so that follow-up is one line, and the build's notice that this dynamic import creates no chunk is expected and quoted in the PR body. No loading or error component: the forms are small and are served by the same host; a failed load is caught by the panel boundary and logged through `describeError`.
- The manifest still reaches no OpenLayers module statically (`no manifest reaches OpenLayers` of `wave2.test.js` passes unedited).

- [ ] **Step 1: Measure the base.** Run: `cd bee-with-me\frontend; npm ci; npm run build; node scripts/initial-js.mjs` (the script is written first; it has no test of its own, its output is compared with the sizes `npm run build` prints for the files `dist/index.html` names). Expected on `090b9cc`: `10 files, 357.66 kB`. Write the printed line into the PR body as "before"; if the base moved, the line of the new base is the "before".
- [ ] **Step 2: Write the failing tests**, each `[T633]`, in `lazy.test.js`: `the popup component of the manifest is an async component` (`popupFor(collectPopups([fire]), 'hotspot').component` has `__asyncLoader`); `the dialogs panel has a retry key that follows the open dialog`; `the fire manifest source imports neither form nor the popup statically` (the text of `index.js` and of `FireDialogs.vue`: no `import FireMapPopup from`, no `import FieldReportForm from`, no `import SuppressionZoneForm from`); `the alarm banner is still imported statically`; `opening the report dialog renders the form after the chunk resolves` (mount `FireDialogs`, `useFireUi().openDialog({ kind: 'report', ... })`, `await flushPromises()`, the form is in the DOM); `a form whose chunk fails is logged once and the next open tries again` (the loader mocked to reject once: `console.error` gets a string, never an object; a second `openDialog` renders the form).
- [ ] **Step 3: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/modules/fire/lazy`. Expected: FAIL (`expected undefined to be defined` for `__asyncLoader`).
- [ ] **Step 4: Implement** the three async imports and the retry key. Then run the fire and map tests; a test that read the popup or a form synchronously gets `await flushPromises()` and nothing else. A test that needs another edit stops the task.
- [ ] **Step 5: Run and measure.** Run: `cd bee-with-me\frontend; npm test; npm run build; node scripts/initial-js.mjs`. Expected: PASS, a clean build, and a figure **lower** than the "before" line; the build output lists the popup and the report form as chunks of their own that `dist/index.html` does not name (the zone form stays where it is, see Interfaces). Write "after" and the difference into the PR body, with the size of `FireZonesSettings` from the same output (open question 3). If the figure is not lower, stop and report: the components are then pulled in by another static import, which the PR must name.
- [ ] **Step 6: Look.** With the stack running in test mode: open a hotspot popup, and once more after a hard reload (empty cache) on a hotspot at the edge of the map: the popup must be fully inside the view (the host positions the overlay one tick after the selection and the chunk arrives later; if the first popup is cut off, the host calls its positioning again when the popup component has mounted, which is an edit of `platform/map-shell/MapPopupHost.vue` added to this task with a test `the overlay is positioned again when a late popup mounts`); then the report dialog from the map menu and from a tracker row, the zone dialog; each opens as before. Then commit `perf(fire): T633 the fire popup and dialogs are loaded on demand`.

dod:
- `cd bee-with-me\frontend; npm test`
- `cd bee-with-me\frontend; npm run build`
- `cd bee-with-me\frontend; node scripts/initial-js.mjs`

### Task 634: one global error handler and one handler for unhandled rejections

**risk:** security
**owner:** implementer
**hardware:** safe
**Files:**
- Create: `frontend/src/platform/errors.js`, `frontend/src/platform/errors.test.js`
- Modify: `frontend/src/main.js` (one import, one call before `app.mount`)

**Why.** `main.js` installs no `app.config.errorHandler` and no `unhandledrejection` listener (`git grep -nE "errorHandler|unhandledrejection" -- frontend/src` prints nothing on `090b9cc`). An error outside a panel boundary, or a rejected promise nobody awaits, is therefore printed by the browser as the raw error object; for an axios error that object carries the request config and with it the bearer token, which is exactly what B99 and B108 removed from the app's own log lines with `platform/describeError.js`. This task closes the two remaining doors.

**Interfaces:**
- Consumes: `describeError(error) -> string` of `platform/describeError.js` (the message and the HTTP status, nothing else).
- Produces `platform/errors.js`: `installErrorHandlers(app, { target = window, log = console.error } = {}) -> () => void`. It sets `app.config.errorHandler = (error, _instance, info) => log(`[app] ${info}: ${describeError(error)}`)`; it adds one `unhandledrejection` listener to `target` that logs `[app] unhandled rejection: ${describeError(event.reason)}` and calls `event.preventDefault()` (so the browser does not print the object as well); it returns a function that removes the listener (for the tests). A handler never throws: `describeError` is called inside a `try`, and on a failure the line is `[app] error (no description)`. It shows nothing on screen and changes no state.
- Produces in `main.js`: `installErrorHandlers(app)` after the plugins and before `app.mount('#app')`.
- Not changed: `PanelBoundary`, `MapPopupHost` and the live dispatch keep their own `onErrorCaptured` and `try` blocks (they return `false` or catch, so their errors do not reach the global handler twice).

- [ ] **Step 1: Write the failing tests**, each `[T634]`, in `errors.test.js`: `a render error of a component outside any boundary is logged as one string` (a component that throws in `setup`, mounted in an app with the handlers: `log` is called once with a string that starts with `[app] `); `the log line of an axios-like error has the message and the status and no token` (an error with `response.status` 500 and `config.headers.Authorization = 'Bearer secret'`: the line contains `HTTP 500` and not `secret`); `an unhandled rejection is logged as a string and its default is prevented` (a fake `target` built on `EventTarget`; an event object with `reason` and a spy `preventDefault`); `a rejection whose reason is not an error is described` (`reason = 'x'`, and `undefined`); `the returned function removes the listener`; `a handler that cannot describe the error still logs one line`; `main.js installs the handlers before it mounts` (the text of `main.js`: `installErrorHandlers(app)` comes before `app.mount`); `an error inside a panel boundary does not reach the global handler` (a throwing panel in `PanelHost`: `log` is not called, the boundary's own line is).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/platform/errors`. Expected: FAIL (`Failed to resolve import "./errors.js"`).
- [ ] **Step 3: Implement** the file and the call in `main.js`.
- [ ] **Step 4: Run.** Run: `cd bee-with-me\frontend; npm test; npm run build; node scripts/initial-js.mjs` (the script of T633; when T633 is not merged yet, read the sizes from the build output instead). Expected: PASS and a clean build; the initial JavaScript grows by the size of one small file, stated in the PR body.
- [ ] **Step 5: Commit** `fix(platform): T634 a global error handler and an unhandled-rejection handler log the message, never the error object`.

dod:
- `cd bee-with-me\frontend; npm test`
- `cd bee-with-me\frontend; npm run build`
