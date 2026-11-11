# Vertical slices, step 3 on the frontend: the `gateway` module and the tracker panel and layers as `tracking` contributions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the gateway status its own frontend module (`frontend/src/modules/gateway/`), and move the last tracking features out of `MapView.vue` and `useMap.js`: the tracker panel becomes a panel of the `tracking` module and the tracker, trail and checkpoint layers become its map entry.

**Architecture:** The same contribution contract as wave 2: a manifest lists live handlers, live hooks, panels and map layers; the map view and the facade read lists and name no module. The gateway status moves first (small, it removes a line of `MapView.vue` and a field of the tracking store). The panel and the layers are the two tasks wave 2 planned as T548 and T549 and postponed; they are re-planned here with new numbers and without line numbers, because the files changed under the old text.

**Tech Stack:** Vue 3 `<script setup>`, Pinia, OpenLayers 10, vitest. No new dependency.

**Spec:** [`docs/superpowers/specs/2026-10-31-vertical-slices-programme-design.md`](../specs/2026-10-31-vertical-slices-programme-design.md) section 5 ("Step 3", frontend part); `Architecture/application/modular-monolith.md` sections 3.2, 5.1 (rule 5), 7; contribution contract: [`2026-11-10-vs-map-shell.md`](2026-11-10-vs-map-shell.md) section 1 and [`2026-11-10-vs-step2-fire.md`](2026-11-10-vs-step2-fire.md) section 1.2; the superseded task texts: [`2026-11-10-vs-step2-tracking-sos.md`](2026-11-10-vs-step2-tracking-sos.md), tasks 548 and 549. Overview: [`2026-11-11-vs-wave3-overview.md`](2026-11-11-vs-wave3-overview.md).

**Base:** `upstream/develop` at `d174ce3`. Wave 2's T545 (the SOS toast as a panel) is **not merged** on this base (`frontend/src/components/SOSToast.vue` still exists and `MapView.vue` imports it); it is the first link of the map chain and is executed from its wave 2 text before T630.

## Global Constraints

- The decisions of wave 2 apply: `frontend-designer` owns every `.vue` and `.css` change; the shell contract of T422 and T423 is not changed; `lib/groups.js` stays; error isolation of contributions stays; `stores/locations.js` stays as the `useLocationsStore` facade with its present names until step 5; every UI text exists in EN and BG; no manifest reaches OpenLayers statically.
- **Hardware:** none of the three tasks touches the backend; all are safe without hardware.
- **One session at a time on `MapView.vue` and `useMap.js`** (the map chain of the overview): T545, T630, T631, T632 in that order.
- No intended difference on screen in any task, except the two named ones: the gateway status is refetched after a reconnect (T630) and a failed tracker layer is said out loud (T632).
- Every frontend PR states the entry chunk size before and after, read from the `npm run build` output of its base and of its head (no figure is written in this plan: wave 2 changed it with every merge).
- Tags: vitest `[T63x]`. Existing tests stay unedited except the edits of section 4; a `MapView*.test.js` or `useMap.*.test.js` file that would need another edit stops the task.
- After every UI task the maintainer runs the impeccable detector by hand (the hook is off).

## Review Focus

1. A marker that is filtered out while its row is visible, or the reverse (BP-01): the list the panel shows and the list the map draws are one computed value of one store (T631, `the rank filter narrows the rows and the list the map gets`).
2. A marker that never goes stale because the 60 second restyle timer did not start or was not cleared (BP-01): T632, `a position that goes stale is restyled by the timer without a new message`, `dispose stops the timer`.
3. A tracker layer that fails to install takes the people off the map without a word (BP-03): T632 shows an alert note; the SOS banner and the panel keep working.
4. The gateway pill shows "connected" for ever after the socket dropped and came back: T630 refetches the status on reconnect.
5. Fire's "report fire at this position" button disappears from the tracker row when the row moves: it becomes a contributed row action and a test clicks it (T631).

---

## 1. Design

### 1.1 The gateway module (T630)

| Today | After |
|-------|-------|
| `serialStatus` and `applySerialStatus` in `modules/tracking/store.js`; `serial_status` in the tracking manifest's `liveHandlers` | `modules/gateway/store.js` (`useGatewayStore`: `status`, `applyStatus(data)`, `fetchStatus()`); the handler in the gateway manifest |
| `MapView.vue` seeds the status once on mount with `getSerialStatus()` | the gateway manifest's `live: { setup: fetchStatus, onReconnect: fetchStatus }`; a failure is swallowed as today (the port may be unconfigured) |
| the pill (`div.serial-status` with its dot and two texts) and its CSS rules in `MapView.vue` | `modules/gateway/components/GatewayStatus.vue`, a `map-root` panel with the same markup, classes and texts |
| texts `map.serialConnected`, `map.serialDisconnected` in the global dictionaries | `gateway.connected`, `gateway.disconnected` in the module's `i18n/en.js` and `bg.js`, the same words |
| `useLocationsStore()` returns `serialStatus` and `applySerialStatus` from tracking | the facade returns the gateway store's `status` under the name `serialStatus` and `applyStatus` under `applySerialStatus`: its names do not change |

The manifest: `name: 'gateway'`, `routes: []`, `nav: []`, `mapLayers: []`, `banners: []`, `panels: [{ id: 'gateway-status', host: 'map-root', order: 20, component: GatewayStatus }]`, `liveHandlers: { serial_status }`, `live` as above, `depends: []`. The component is imported statically (a few lines, no `ol`). The word "frames" after the counter is a hard-coded English word in today's template; it moves as it is and is reported, not translated, in this task.

### 1.2 The tracker panel (T631, was T548)

The panel is not only markup: the filtered list is also the list the map draws, and a row carries fire's "report fire at this position" button. So the move needs shared state and one more contribution point.

- `modules/tracking/ui.js`: a Pinia store `useTrackerUi` with `viewMode`, `rankFilter`, `selectedDeviceId`, `groupsMap` (set by the view, which already loads the teams), `displayList`, `groupsWithLeaders` (today's computations, reading the tracking store) and `select(deviceId)`.
- A new optional manifest field `actions`: items `{ id, target, order, labelKey, testId?, isAvailable?: (subject) => boolean, onSelect: (subject) => void }`; `collectActions(modules, target, legacy = [])` in `platform/map-shell/contributions.js`, sorted by `order`, then `id`; `validateManifest` names a malformed item. Fire contributes `{ id: 'fire-report-at-position', target: 'tracker-row', order: 10, labelKey: <the key of today's button>, testId: 'report-fire-row', onSelect: <today's reportFromRow with its 24 hour rule> }`.
- `modules/tracking/components/TrackerPanel.vue` (prop `context`): the mode toggle and the tracker `aside` with their markup, classes and test ids; the 10 second tick for the age labels, started on mount and cleared on unmount; the row actions from `collectActions(MODULES, 'tracker-row')`. It is a panel of the tracking manifest on the host the map view's panel column uses today (read `PANEL_HOSTS` in `platform/map-shell/contributions.js`; a new host name is added only if none fits, and then to that list and its test).
- `MapView.vue` passes `useTrackerUi().displayList` to `useMap` where it passes its own computed list today, and its marker-click callback calls `useTrackerUi().select`.

### 1.3 The tracker layers (T632, was T549)

- `modules/tracking/map/layers.js`: `TRACKING_MAP_LAYERS` with the ids `tracking-trail`, `tracking-checkpoints`, `tracking-trackers` and the z-indices `Z.trail`, `Z.checkpoints`, `Z.trackers` of `platform/map-shell/zorder.js`.
- `modules/tracking/map/index.js`: default export `{ name: 'tracking', layers, setup: setupTrackingMap }`; `setupTrackingMap(shell, ctx)` returns `{ api: { setPositions(list), setTrails(trailMap), setGroups(groupsMap), setShowPhotos(on), setTrailVisible(on), setCheckpointNumbers(on), refreshMarkers(list), trackerHit(pixel) }, dispose }`. It owns the marker, photo, trail and checkpoint styles, the tooltip overlay and its pointer handler, the tracker click handler (today's rule and order), the photo-loaded restyle and the 60 second stale timer (started in `shell.onMounted`, cleared in `dispose`).
- `useMap.js` keeps its parameters and returned names; its watchers call the entry's api; `makeMarkerStyle` and `makePhotoMarkerStyle` stay importable from `useMap.js` as re-exports; when the tracking entry failed to install, `refreshMarkers` returns `false`.
- `MapView.vue`: when `refreshMarkers` returns `false`, a note with `role="alert"` shows the new text `map.trackerLayerFailed` (EN "The tracker layer could not be loaded. Reload the page.", BG "Слоят с тракерите не се зареди. Презаредете страницата.") where the stale-feed banner sits. The repeater layer, the measure layer, the graticule, the basemaps and the weather tile layer stay in the facade (step 5).

## 2. File map and chains

Commands used: `git grep -nE "serialStatus|applySerialStatus|serial_status|getSerialStatus|serialConnected|serialDisconnected" -- frontend/src`; `git grep -nE "tickTimer|staleTimer|displayList|rankFilter|viewMode|reportFromRow" -- frontend/src/views/MapView.vue frontend/src/composables/useMap.js`; `ls frontend/src/views/MapView*.test.js frontend/src/composables/useMap.*.test.js`.

| File | This plan | Also touched by |
|------|-----------|-----------------|
| `frontend/src/views/MapView.vue` (hot, map chain) | T630 (pill, seed call, CSS), T631 (panel block and its state), T632 (one note) | wave 2 T545 first |
| `frontend/src/composables/useMap.js` (hot, map chain) | T632 | none |
| `frontend/src/modules/index.js`, `frontend/src/i18n/en.js`, `bg.js` (assembly chain) | T630 (one line; two keys leave), T632 (one key) | wave 2 T545 does not touch them |
| `frontend/src/modules/tracking/index.js`, `store.js` | T630 (the status leaves), T631 (`panels`, `useTrackerUi`), T632 (`mapLayers`) | none |
| `frontend/src/stores/locations.js` | T630 (two names re-pointed) | none |
| `frontend/src/platform/manifest.js`, `platform/map-shell/contributions.js` | T631 (`actions`) | none |
| `frontend/src/modules/fire/index.js` | T631 (one action) | none |
| `frontend/src/modules/mapEntries.js` | T632 | none |

## 3. Task order, PRs, reviewers

| PR | Task | Content | Needs | Owner | Reviewers | Hardware |
|----|------|---------|-------|-------|-----------|----------|
| (wave 2) | T545 | the SOS toast is a panel | nothing | frontend-designer | breaker | safe |
| 1 | T630 | frontend `gateway` module: status store, live handler, pill | T545 merged (map chain) | frontend-designer | breaker | safe |
| 2 | T631 | the tracker panel is a `tracking` panel | T630 | frontend-designer | breaker | safe |
| 3 | T632 | tracker, trail and checkpoint layers are the `tracking` map entry | T631 | frontend-designer | breaker | safe |

The plan does not depend on any backend task of wave 3 and can run from the first day, one PR after the other. Every PR: `npm test`, `npm run build`, `python tools/smoke.py` (step f, the frontend image), a manual look at the map page with test mode running (markers, trail, tooltip, panel, SOS, the gateway pill), then `breaker`; `gh pr create` by the human.

**Rollback.** `git revert -m 1 <merge>`, newest first (T632, T631, T630). **Not verified while planning:** no browser was opened; that a Pinia store (`useTrackerUi`) read by both the panel and the view keeps `displayList` identical for both is T631 step 4; which panel host the tracker column needs is read in T631 step 1.

## 4. Existing tests

| File | Edit | Kind | Task |
|------|------|------|------|
| `frontend/src/composables/useWebSocket.dispatch.test.js` | the table row `['serial_status', loc, 'applySerialStatus']` points at a mock of `../modules/gateway/store.js` with the spy `applyStatus` | mock path | T630 |
| `frontend/src/modules/tracking/index.test.js` | a case that expects `serial_status` among the tracking handlers expects it in the gateway manifest instead (the case moves to `modules/gateway/index.test.js`) | deliberate: the handler moved | T630 |
| the i18n tests (`no text key was lost`, parity, collisions) | none: two keys move to a module dictionary with the same words; if `no text key was lost` compares key names and fails, the two old names are added to its rename table as wave 2 did for `sos` | none or a rename entry | T630 |

Every `MapView*.test.js` and `useMap.*.test.js` file stays unedited (they mock or call the facade, whose names do not change).

## 5. Open questions (details in the overview, section 7)

1. **To the maintainer:** T631 and T632 were optional in wave 2. Default of this plan: T630 and T631 run; T632 runs last and may be dropped without leaving anything half-moved (the layers then stay in the facade until step 5).
2. **To the maintainer:** translate the word "frames" in the gateway pill (a new key `gateway.frames`) in T630 or leave it (default: leave, report).

---

### Task 630: the frontend `gateway` module (status store, live handler, the pill)

**risk:** normal
**owner:** frontend-designer
**hardware:** safe
**Files:**
- Create: `frontend/src/modules/gateway/{index.js, store.js, i18n/en.js, i18n/bg.js, components/GatewayStatus.vue, index.test.js, store.test.js, components/GatewayStatus.test.js}`
- Modify: `frontend/src/modules/index.js` (one line, alphabetical: after `fire`), `frontend/src/i18n/en.js`, `bg.js` (`map.serialConnected`, `map.serialDisconnected` leave)
- Modify: `frontend/src/modules/tracking/index.js`, `store.js` (the status and its handler leave), `frontend/src/stores/locations.js` (two names re-pointed)
- Modify: `frontend/src/views/MapView.vue` (the pill block, the seed call in the mount hook, the `.serial-*` CSS rules, the `getSerialStatus` import)
- Modify: the tests of section 4

**Interfaces:**
- Consumes: the live dispatch and its hooks (`live.setup`, `live.onReconnect`), the `map-root` panel host, `getSerialStatus` of `src/api`.
- Produces: the store, the manifest and the panel of section 1.1. `fetchStatus()` never throws. `GatewayStatus.vue` declares the `context` prop, renders nothing while `status` is `null`, and shows the connected or the disconnected text with the port and, when connected, the frame counter, exactly as today.

- [ ] **Step 1: Read, then write the failing tests.** Read the `MapView*.test.js` files for a query on `.serial-status` or a mock of `getSerialStatus` and keep each working. Tests, each `[T630]`. `store.test.js`: `applyStatus replaces the status`; `fetchStatus stores the answer`; `a failed fetchStatus leaves the status and does not throw`. `index.test.js`: `the gateway manifest is valid and in the module list`; `serial_status is handled by gateway and not by tracking`; `the status is fetched in setup and again on reconnect` (run the collected hooks of the real module list with `getSerialStatus` mocked: one call per hook run); `the facade still returns serialStatus and applySerialStatus` (a status applied through `useLocationsStore().applySerialStatus` is read from `useGatewayStore().status`). `GatewayStatus.test.js`: `shows connected with port and counter`; `shows disconnected with the port`; `renders nothing without a status`; `the root element carries no context attribute`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/modules/gateway`. Expected: FAIL (`Failed to resolve import "./store.js"`).
- [ ] **Step 3: Move** the state, the handler, the pill with its CSS and the two texts; write the manifest and the list line; apply the test edits of section 4.
- [ ] **Step 4: Run.** Run: `cd bee-with-me\frontend; npm test; npm run build`. Expected: PASS and a clean build; the unedited `stores/locations.test.js` and `MapView*.test.js` files pass.
- [ ] **Step 5: Commit** `refactor(gateway): T630 the gateway status is a frontend module with its own store, handler and panel`. PR body: the one behaviour difference (the status is refetched after a reconnect), the chunk size before and after.

dod:
- `cd bee-with-me\frontend; npm test`
- `cd bee-with-me\frontend; npm run build`

### Task 631: the tracker panel becomes a panel of the tracking module (was T548)

**risk:** normal
**owner:** frontend-designer
**hardware:** safe
**Files:**
- Create: `frontend/src/modules/tracking/ui.js`, `modules/tracking/components/TrackerPanel.vue`, `modules/tracking/components/TrackerPanel.test.js`, `modules/tracking/ui.test.js`
- Modify: `frontend/src/modules/tracking/index.js` (`panels`, the named export `useTrackerUi`), `frontend/src/platform/manifest.js`, `platform/manifest.test.js`, `platform/map-shell/contributions.js`, `contributions.test.js` (`actions`), `frontend/src/modules/fire/index.js` (one action)
- Modify: `frontend/src/views/MapView.vue` (the mode toggle and the tracker `aside` in the template; in the script the state and functions named `viewMode`, `rankFilter`, `nowTick`, `tickTimer`, `rankFiltered`, `displayList`, `groupsWithLeaders`, `selectedDeviceId`, `selectDevice`, `reportFromRow`, `setViewMode`, `focusDevice`, `formatTime`, `batClass`; the panel's CSS rules)

**Interfaces:**
- Consumes: the panel hosts and the map context of wave 2, `useFireUi` of the fire module, `useTrackingStore`.
- Produces: `useTrackerUi`, the `actions` contribution point with `collectActions`, fire's `fire-report-at-position` action and `TrackerPanel.vue`, all as section 1.2 says.

- [ ] **Step 1: Read, then write the failing tests.** Read the `MapView*.test.js` files for every query on `.tracker-row`, `.tracker-panel`, `[data-testid="report-fire-row"]`, the rank filter and the mode toggle, and keep each. Read `PANEL_HOSTS`. Tests, each `[T631]`. `ui.test.js`: `displayList follows the rank filter`; `the teams view gives one leader row per team`; `select sets the selected device`. `TrackerPanel.test.js`: `rows come out by urgency and show name, MGRS, age and battery`; `the rank filter narrows the rows and the list the map gets` (the same `displayList` object is read by the panel and by a second consumer); `the age label of a row changes class when its position goes stale, without a new message` (fake timers, the 10 second tick); `a selected row offers the row actions of the modules and a click runs fire's action`; `unmount clears the tick timer`. `contributions.test.js`: `actions are collected per target and sorted by order then id`. `manifest.test.js`: `validateManifest accepts actions and names a malformed one`.
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
- Create: `frontend/src/modules/tracking/map/layers.js`, `modules/tracking/map/index.js`, `modules/tracking/map/trackerLayers.test.js`
- Modify: `frontend/src/modules/tracking/index.js` (`mapLayers`), `frontend/src/modules/mapEntries.js`
- Modify: `frontend/src/composables/useMap.js` (the tracker, trail and checkpoint sources, layers, styles and upserts; the tooltip overlay and its handler; the tracker click handler; `staleTimer`; the watchers on the position list, the trails and the photo switch), `frontend/src/views/MapView.vue` (one note), `frontend/src/i18n/en.js`, `bg.js` (one key)

**What moves and why it is a task of its own.** It is the largest single cut of `useMap.js` and it is BP-01 directly: a marker that is not drawn, or not restyled when it goes stale, is a person the operator cannot see.

**Interfaces:**
- Consumes: `shell.install`, `shell.onMounted`, `shell.onClick`, `shell.onPointerMove` and the `ctx` of the map shell (shape unchanged); `Z.trail`, `Z.checkpoints`, `Z.trackers`; the libraries of `modules/tracking/lib/`.
- Produces: the layer list, the map entry and its api, the facade's delegation and the failure note, all as section 1.3 says; the text `map.trackerLayerFailed` in both languages.

- [ ] **Step 1: Read, then write the failing tests.** Read every `useMap.*.test.js` file; they call the real composable and are the net. Tests in `trackerLayers.test.js`, each `[T632]`, with a shell as in the map-shell tests: `the three layers are registered with the z-indices of the z-order table`; `positions set before mount are drawn after mount`; `a position that goes stale is restyled by the timer without a new message` (fake timers, 60 seconds); `dispose stops the timer and removes the tooltip overlay`; `a tracker under the pointer shows the tooltip in every mode`; `a failed install makes refreshMarkers return false and the view shows the alert note` (the entry's `setup` replaced by one that throws).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/modules/tracking/map`. Expected: FAIL (`Failed to resolve import "./index.js"`).
- [ ] **Step 3: Move** the code in this order, running `npm test -- src/composables` after each: styles; sources, layers and upserts; tooltip and click handlers; the timer and the watchers; the failure note.
- [ ] **Step 4: Run** the unedited `useMap.*.test.js` and `MapView*.test.js` files and the rest. Run: `cd bee-with-me\frontend; npm test; npm run build`. Expected: PASS and a clean build; the entry chunk did not take in OpenLayers (`no manifest reaches OpenLayers` passes).
- [ ] **Step 5: Commit** `refactor(tracking): T632 tracker, trail and checkpoint layers are the tracking module's map entry`.

dod:
- `cd bee-with-me\frontend; npm test`
- `cd bee-with-me\frontend; npm run build`
