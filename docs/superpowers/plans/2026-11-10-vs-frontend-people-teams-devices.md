# Vertical slices: frontend modules `people`, `teams`, `devices` (ahead of their backends) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the frontend modules `people`, `teams` and `devices` from `UsersView`, `GroupsView`, `DevicesView` and `lib/groups.js`, on the REST endpoints that exist today, fix B77 and B78 in them, and add their stores, without any backend change.

**Architecture:** One preparation task does every edit of the shared files once (the three manifests with routes, navigation and i18n namespaces; the router, the navigation list, the two dictionaries and the module list), with the manifests still pointing at the views in `src/views/`. After it, each module's view move touches only that module's folder, so the three moves run in parallel. Bug fixes follow their move as separate PRs, so a move stays a pure move. Stores come last and are new code with no consumer in this wave.

**Tech Stack:** Vue 3 `<script setup>`, Pinia, vue-router 4, vue-i18n 11, vitest with `@vue/test-utils`. No new dependency.

**Spec:** [`docs/superpowers/specs/2026-10-31-vertical-slices-programme-design.md`](../specs/2026-10-31-vertical-slices-programme-design.md) (section 5 "Step 3": frontend `people`, `teams` and `devices` are created ahead of their backends; section 6), `Architecture/application/modular-monolith.md` sections 3.2, 3.3, 4.1. Template: [`2026-11-10-vs-step1-settings.md`](2026-11-10-vs-step1-settings.md) section 1 (anatomy 1.2, moving files 1.3). Bugs: [`2026-10-31-vs-phase0-1.bugs.md`](2026-10-31-vs-phase0-1.bugs.md) (B77, B78). Wave overview: [`2026-11-10-vs-wave1-overview.md`](2026-11-10-vs-wave1-overview.md).

**Base:** `upstream/develop` at `2472543` plus plan 1's T403 (module assembly), which must be merged first. Execution branches: `feature/vs-fe-<task>` off `develop`, one PR per task.

## Global Constraints

- No backend file changes. Only REST endpoints that exist: `GET /api/users/` (`limit` up to 500, `offset`), `GET /api/groups/` (`include_members`, `limit` up to 500), `GET /api/devices/`, and the write endpoints the views already call.
- `.vue` files are changed only by the `frontend-designer` agent (T441, T442, T443, B77, B78). `.js` files (manifests, i18n, router, stores) are not routed (T440, T444).
- A move changes nothing visible: same markup, classes, texts, requests and their parameters. The two bug fixes are the only behaviour changes and each has its own PR.
- `frontend/src/views/MapView.vue`, `frontend/src/composables/useMap.js` and `frontend/src/components/AppLayout.vue` are not edited (plan 2 owns them in this wave). The map keeps calling `getGroupsWithMembers` and `getDevices` itself until step 3.
- Old import paths that a non-moved file still uses stay as re-exports (`export * from '<new path>'` as the only statement) until step 5. Views have no other importer than the router, so they leave nothing behind.
- Every existing test stays green and unedited except relative import and `vi.mock` paths in the six test files that move with their view.
- Every UI string is in both languages; a module's strings live in its own `i18n/en.js` and `i18n/bg.js`.
- Tags: vitest `it('... [T44x]', ...)`, bugs `[B77]`, `[B78]`. Commits: `type(scope): T44x summary` or `fix(scope): B7x summary`, body ends with the Co-Authored-By line of the session.

## Review Focus

1. The first load of a page fails (backend not up yet, start.ps1 opens the browser early): the page must say so and must not leave an unhandled promise rejection or a blank table (BP-03) (B77).
2. A load fails, then succeeds: the old error text must be gone (B78), and a failed reload must not wipe the rows already on screen (B77, B78).
3. More people or teams than one request returns (500): a store must not present a cut list as complete (T444, `truncated`).
4. The admin-only rule of a route and of its navigation item must survive the move into a manifest; none of the three pages is admin-only today and none becomes so (T440).
5. Two fast reloads answer out of order: the store keeps the answer of the latest call, not of the slowest (T444).

---

## 1. File map and who else touches each file (as of `2472543`)

Commands used: `git grep -nE "(from|import\() *'[^']*(views/(Users|Groups|Devices)View|lib/groups)" -- frontend/src`, `git grep -nE "\bt\(\s*['\"](users|groups|devices)\." -- frontend/src`, `git grep -n "vi.mock(" -- "frontend/src/views/{Users,Groups,Devices}View*.test.js"`.

| File | This plan | Also read or written by |
|------|-----------|-------------------------|
| `frontend/src/router/index.js` (security-critical) | T440 deletes the `users`, `groups`, `devices` children | plan 1: T403 rewrites the children array, T404 deletes `settings` |
| `frontend/src/nav-config.js` | T440 deletes three items | plan 1 (T403, T404); `AppLayout.vue` reads it |
| `frontend/src/i18n/en.js`, `bg.js` (hot) | T440 takes out `users` (lines 84 to 137 of `en.js`), `groups` (138 to 169), `devices` (170 to 197) and three `nav` lines | plan 1 (T403 wraps the literal, T404 takes out `settings`); 17 test files import `en.js` and keep getting the merged dictionary |
| `frontend/src/modules/index.js` | T440 adds three lines | plan 1 (T403 creates, T404 adds `settings`); plan 2 reads it |
| `frontend/src/views/UsersView.vue`, `UsersView.test.js`, `UsersView.b69.test.js` | T441 moves; B78 fixes `load` | imports `api`, `api/client`, `stores/locations` (stay) |
| `frontend/src/views/GroupsView.vue`, `GroupsView.test.js`, `GroupsView.b70.test.js` | T442 moves; B77 fixes `load`, `selectGroup`, member save | uses one `users.*` key (served by the merged dictionary) |
| `frontend/src/views/DevicesView.vue`, `DevicesView.test.js`, `DevicesView.b70.test.js` | T443 moves; B77 fixes `load` | imports `stores/locations` (stays) |
| `frontend/src/lib/groups.js` | T442 moves it, leaves a re-export | `composables/useMap.js:24`, `stores/locations.js` (through the re-export; neither is edited) |
| new: `frontend/src/modules/{people,teams,devices}/{index.js,i18n/en.js,i18n/bg.js,store.js}` and tests | T440, T444 | step 3 reads the stores; step 4 adds the backends |
| `docs/superpowers/plans/2026-10-31-vs-phase0-1.bugs.md` | B77 and B78 set `status: fixed (<sha>)` | other bug sessions append entries: edit only the two status lines |

Not touched: `api/index.js`, `api/client.js`, `stores/locations.js`, `stores/auth.js`, `platform/**`, `architecture.test.js`, `.dependency-cruiser.cjs`, every backend file.

## 2. Task order, PRs, reviewers, parallel work

| PR | Task | Content | Needs | Owner | Reviewers |
|----|------|---------|-------|-------|-----------|
| 1 | T440 | three manifests, i18n namespaces, routes and navigation through the manifests | T403 (plan 1) | implementer | breaker + security-reviewer (`src/router/**`) |
| 2 | T441 | move `UsersView` into `people` | T440 | frontend-designer | breaker |
| 3 | T442 | move `GroupsView` and `lib/groups.js` into `teams` | T440 | frontend-designer | breaker |
| 4 | T443 | move `DevicesView` into `devices` | T440 | frontend-designer | breaker |
| 5 | B78 | `UsersView` drops a stale load error | T441 | frontend-designer | breaker |
| 6 | B77 | first load and group selection are guarded in `GroupsView` and `DevicesView` | T442, T443 | frontend-designer | breaker |
| 7 | T444 | stores of the three modules | T440 | implementer | breaker |

**Inside the plan.** T440 is alone and first: it is the only task that edits the four shared files. T441, T442, T443 and T444 then touch disjoint folders (`modules/people/views`, `modules/teams/views` and `lib`, `modules/devices/views`, the three `store.js` files) and run in parallel, up to four at a time; each also changes one line of its own manifest (the lazy import path), which T444 does not touch. B78 follows T441; B77 follows T442 and T443 (it edits both moved views and both modules' dictionaries).

**Against the other two plans.**

| File pair | Who | Conflict and resolution |
|-----------|-----|-------------------------|
| `src/modules/index.js` | T440 and T404 | adjacent lines; keep both, alphabetical |
| `src/router/index.js`, `src/nav-config.js` | T440 and T404 | T440 deletes the `users`, `groups`, `devices` lines, T404 the `settings` line; two unchanged lines lie between them, so git merges them cleanly; if not, keep both deletions |
| `src/i18n/en.js`, `bg.js` | T440 and T404 | different namespaces; keep both deletions; the collision and parity tests (T403) and the before/after leaf count show the result |
| `src/lib/groups.js` | T442 (re-export) and plan 2 | plan 2 does not edit `lib/groups.js`; `useMap.js` line 24 keeps its import |
| `MapView.vue`, `useMap.js`, `AppLayout.vue` | plan 2 only | this plan never edits them |

Order between T404 and T440: whichever is merged second merges `upstream/develop` into its branch (no rebase) and reruns its DoD. Preferred: T404 first, because it is the template the three manifests copy.

**PR gate (every PR), in this order:** (1) the task's DoD; (2) `cd bee-with-me\frontend; npm test; npm run build`; (3) `python tools/smoke.py` (step d reads `/api/users/` and `/api/devices/`, step f serves the built SPA), PASS lines in the PR body; (4) for the `frontend-designer` tasks: a manual look at the page in the dev stack by the maintainer (list, add, edit, error text), as a checkbox in the PR body, and a reminder to run the impeccable detector; (5) `breaker` and, for T440, `security-reviewer` on the head commit until `VERDICT: PASS`; (6) `gh pr create` is run by the human with `--body-file`.

## 3. Risks, rollback, not verified

| Risk | Mitigation |
|------|------------|
| A manifest route points at a view that another branch moves at the same moment | T440 points at `src/views/`; each move changes its own manifest line in the same commit as the `git mv`; the build fails on an unresolved lazy import |
| A test mocks a path that becomes a re-export | only `lib/groups.js` gets one; `git grep -n "vi.mock('[^']*lib/groups" -- frontend/src` prints nothing today and is rerun in T442 |
| B77 changes what the operator sees on a failed load | intended; a red error text instead of a blank table; own PR, stated in the PR body |
| The stores have no consumer until step 3 and their shape is a guess | T444 is the last PR, small and detachable; section 5 item 1 asks whether to build it now |
| bee-dev gets a broken page | smoke plus the manual check of the PR gate; `git revert -m 1 <merge>` |

**Rollback.** Frontend only: `git revert -m 1 <merge commit>`, newest first (T444, B77, B78, the moves in any order, T440 last because the moves edit its manifests).

**Not verified while planning:**
- The exact member-save paths of `GroupsView.vue` that B77 names (lines 281 to 347 were read at the level of their `catch` clauses only); B77 step 1 reads them.
- The response shape of `GET /api/devices/` was taken from the views (`getDevices()` resolves to an array) and of the two paged lists from `routers/users.py` and `routers/groups.py` (`{ items, total }`); T444 step 1 confirms `total` for groups.
- No browser was opened while planning.

## 4. Existing tests

`UsersView.test.js`, `UsersView.b69.test.js`, `GroupsView.test.js`, `GroupsView.b70.test.js`, `DevicesView.test.js`, `DevicesView.b70.test.js` move with their view and change only relative paths: `'../api'` to `'../../../api'`, `'../api/client'` to `'../../../api/client'`, `'../stores/locations'` to `'../../../stores/locations'`, `'../i18n/index.js'`, `'../i18n/en.js'`, `'../i18n/bg.js'` to `'../../../i18n/...'` (the merged dictionaries), in imports and in `vi.mock(...)`. All other test files are unedited. The T403 tests of plan 1 (`modules.test.js` and `router/moduleRoutes.test.js`: no text key was lost against `i18n/keys.snapshot.json`, valid list, folders and list agree, key parity, no collision, merged dictionary equals core plus module files, navigation order, re-exports are pure, the real router serves every module route) run against every task of this plan and must stay green. T440 reads the `i18n leaves en=<n> bg=<n>` line that `modules.test.js` prints, on the branch and on its base (both numbers equal, in the PR body); B77 adds exactly 2 keys per language (`groups.loadError`, `devices.loadError`).

## 5. Open to the owner and hand-offs

1. **Stores now or in step 3?** The spec creates these modules so that they "supply names, teams and photos to the map" in step 3, when the live payload goes thin. T444 builds the stores now, without a consumer, because the task list asks for them. The alternative is to drop T444 and let step 3 write them with their first consumer. Recommendation: keep T444 small as written, or drop it; do not grow it.
2. **More than 500 people or teams.** One request returns at most 500 rows; the views already ask for 500 and ignore the rest. The stores report `truncated` instead of paging. Paging in the stores is a step 3 decision (it depends on how the map joins names).
3. **`users`, `groups` naming.** The modules are `people` and `teams`; routes (`/users`, `/groups`), i18n namespaces (`users.*`, `groups.*`) and API paths keep today's names, so nothing visible changes. Renaming them is a later, separate decision.
4. **`lib/groups.js` is about live positions.** `normaliseGroups` repairs the `groups` column of a position row (B50) and is used by `useMap.js` and `stores/locations.js`; by content it belongs to `tracking` (step 3). This plan moves it into `teams` because the task list says so; the alternative is to leave it in `src/lib/` until step 3 and save one move. T442 keeps it in its own commit so it can be dropped.
5. **B78 is fixed by clearing the error on success**, not at the start of `load()` as the bug entry words it (reason in the task).
6. **B77 and B78 status lines** in the phase 0-1 bugs file are set by the fixing PRs; the bugs file is shared with other sessions.
7. **To the architecture owner (text proposal, not edited here):** modular-monolith.md section 9 notes that the frontend `people`, `teams`, `devices` modules exist from wave 1 (the spec placed them in step 3).

---

### Task 440: manifests, dictionaries, routes and navigation of `people`, `teams`, `devices`

**risk:** security
**owner:** implementer
**Files:**
- Create: `frontend/src/modules/people/index.js`, `frontend/src/modules/people/i18n/en.js`, `frontend/src/modules/people/i18n/bg.js`
- Create: `frontend/src/modules/teams/index.js`, `frontend/src/modules/teams/i18n/en.js`, `frontend/src/modules/teams/i18n/bg.js`
- Create: `frontend/src/modules/devices/index.js`, `frontend/src/modules/devices/i18n/en.js`, `frontend/src/modules/devices/i18n/bg.js`
- Modify: `frontend/src/modules/index.js` (three lines), `frontend/src/router/index.js` (delete the `users`, `groups`, `devices` children), `frontend/src/nav-config.js` (delete the three items), `frontend/src/i18n/en.js` and `bg.js` (delete the three namespaces and the three `nav` lines)
- Test: `frontend/src/modules/people-teams-devices.test.js`

**Interfaces:**
- Consumes: `MODULES`, `collectRoutes`, `collectNav`, `mergeMessages`, `validateManifest` and the `modules.test.js` invariants (plan 1, T403).
- Produces three default-exported manifests, each importing only its two dictionaries:
  - `people`: `routes: [{ path: '/users', name: 'users', component: () => import('../../views/UsersView.vue') }]`, `nav: [{ to: '/users', labelKey: 'nav.users', icon: '👤', order: 20 }]`, `i18n` = `{ nav: { users }, users: { ... } }`.
  - `teams`: `routes: [{ path: '/groups', name: 'groups', component: () => import('../../views/GroupsView.vue') }]`, `nav: [{ to: '/groups', labelKey: 'nav.groups', icon: '👥', order: 30 }]`, `i18n` = `{ nav: { groups }, groups: { ... } }`, `depends: ['people']`.
  - `devices`: `routes: [{ path: '/devices', name: 'devices', component: () => import('../../views/DevicesView.vue') }]`, `nav: [{ to: '/devices', labelKey: 'nav.devices', icon: '📡', order: 40 }]`, `i18n` = `{ nav: { devices }, devices: { ... } }`, `depends: ['people']`.
  - All three: `mapLayers: []`, `panels: []`, `banners: []`, `liveHandlers: {}`; `people` has `depends: []`. No route has `meta.adminOnly` and no nav item has `adminOnly` (as today).
- The texts move verbatim; the icons are copied from `nav-config.js`.

- [ ] **Step 1: Write the failing tests**, each `[T440]`: `the three manifests are valid` (`validateManifest` gives `[]` for each); `their routes are the old paths, named, not admin-only` (paths `/users`, `/groups`, `/devices`; names `users`, `groups`, `devices`; no `meta.adminOnly`); `their navigation items keep place and icon` (orders 20, 30, 40 and the three icons; none has `adminOnly`); `teams and devices depend on people` (the `depends` arrays above; every dependency is a module in `MODULES`); `the texts are in the merged dictionaries in both languages` (`en.users`, `en.groups`, `en.devices`, `en.nav.users`, `en.nav.groups`, `en.nav.devices` are defined in `src/i18n/en.js`, the same for `bg.js`, and `en.nav.users !== bg.nav.users`); `the router serves the three pages under the layout` (with `vi.mock('../api', ...)` as `router/index.test.js` does and the real router of `src/router/index.js`: `router.resolve('/users')` has `matched.length === 2`, the name `users` and no `meta.adminOnly`, the same for `/groups` and `/devices`; `await guard(router.resolve('/users'))` is `undefined` for a viewer with a token).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/modules/people-teams-devices.test.js`. Expected: FAIL (`Failed to resolve import "./people/index.js"`).
- [ ] **Step 3: Implement.** Cut the three namespaces and the three `nav` lines out of `en.js` and `bg.js` into the six module dictionaries; write the manifests; add the three `MODULES` lines (alphabetical: `devices`, `people`, `settings`, `teams`); delete the three router children and the three static nav items.
- [ ] **Step 4: Run** the new test, the T403 invariants and the six view tests (they still sit in `src/views/` and read the merged dictionaries). Run: `cd bee-with-me\frontend; npm test -- src/modules src/platform src/router src/i18n src/views src/components/AppLayout.test.js src/architecture.test.js; npm run build`. Expected: PASS and a clean build with the three view chunks. The `i18n leaves` line printed by `modules.test.js` shows the same two numbers as on the base.
- [ ] **Step 5: Commit** `refactor(modules): T440 people, teams and devices contribute their routes, navigation and texts`.

dod:
- `cd bee-with-me\frontend; npm test -- src/modules src/platform src/router src/i18n src/views src/components/AppLayout.test.js src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`

### Task 441: move `UsersView` into the `people` module

**risk:** normal
**owner:** frontend-designer
**Files:**
- Move: `frontend/src/views/UsersView.vue`, `UsersView.test.js`, `UsersView.b69.test.js` to `frontend/src/modules/people/views/`
- Modify: `frontend/src/modules/people/index.js` (the lazy import becomes `() => import('./views/UsersView.vue')`)
- Test: `frontend/src/modules/people/views/UsersView.moved.test.js`

**Interfaces:**
- Consumes: the `people` manifest (T440).
- Produces: the same component under the new path, file name `UsersView.vue`; no file is left in `src/views/` for it.

- [ ] **Step 1: Write the failing test**: `it('the people route loads the view from the module [T441]')` (`const mod = await manifest.routes[0].component()`; `mod.default.__name === 'UsersView'`; `fs.existsSync` of `src/views/UsersView.vue` is `false` and of `src/modules/people/views/UsersView.vue` is `true`).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/modules/people/views/UsersView.moved.test.js`. Expected: FAIL (the view is still in `src/views/`).
- [ ] **Step 3: Move** with `git mv`; change only relative paths in the view and its two tests (section 4); change the manifest line.
- [ ] **Step 4: Run.** Run: `cd bee-with-me\frontend; npm test -- src/modules src/architecture.test.js; npm run build`. Expected: PASS and a clean build.
- [ ] **Step 5: Commit** `refactor(people): T441 move UsersView into the people module`.

dod:
- `cd bee-with-me\frontend; npm test -- src/modules src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`

### Task 442: move `GroupsView` and `lib/groups.js` into the `teams` module

**risk:** normal
**owner:** frontend-designer
**Files:**
- Move: `frontend/src/views/GroupsView.vue`, `GroupsView.test.js`, `GroupsView.b70.test.js` to `frontend/src/modules/teams/views/`
- Move: `frontend/src/lib/groups.js` to `frontend/src/modules/teams/lib/groups.js`
- Create: `frontend/src/lib/groups.js` (`export * from '../modules/teams/lib/groups.js'`)
- Modify: `frontend/src/modules/teams/index.js` (lazy import path)
- Test: `frontend/src/modules/teams/lib/groups.test.js`, `frontend/src/modules/teams/views/GroupsView.moved.test.js`

**Interfaces:**
- Consumes: the `teams` manifest (T440).
- Produces: `normaliseGroups(pos)` unchanged, reachable from both paths as the same function. `useMap.js` and `stores/locations.js` are not edited.

- [ ] **Step 1: Write the failing tests**, each `[T442]`: `the teams route loads the view from the module` (as in T441, for `GroupsView`); `normaliseGroups is the same function on the old and the new path`; `normaliseGroups turns a JSON string, a broken string and a non-array into an array and leaves an array alone` (`{ groups: '[{"id":1}]' }` gives `[{ id: 1 }]`; `{ groups: '{' }` gives `[]`; `{ groups: 5 }` gives `[]`; an object whose `groups` is an array is returned as the same object; `null` is returned as `null`).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/modules/teams`. Expected: FAIL (`Failed to resolve import "./groups.js"`).
- [ ] **Step 3: Check, then move.** `git grep -n "vi.mock('[^']*lib/groups" -- frontend/src` prints nothing. `git mv` the four files, change only relative paths, write the re-export and the manifest line.
- [ ] **Step 4: Run** the module, the two unedited importers' tests and the re-export purity check. Run: `cd bee-with-me\frontend; npm test -- src/modules src/stores src/composables src/architecture.test.js; npm run build`. Expected: PASS and a clean build.
- [ ] **Step 5: Commit** in two commits: `refactor(teams): T442 move the groups helper into the teams module` and `refactor(teams): T442 move GroupsView into the teams module`.

dod:
- `cd bee-with-me\frontend; npm test -- src/modules src/stores src/composables src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`

### Task 443: move `DevicesView` into the `devices` module

**risk:** normal
**owner:** frontend-designer
**Files:**
- Move: `frontend/src/views/DevicesView.vue`, `DevicesView.test.js`, `DevicesView.b70.test.js` to `frontend/src/modules/devices/views/`
- Modify: `frontend/src/modules/devices/index.js` (lazy import path)
- Test: `frontend/src/modules/devices/views/DevicesView.moved.test.js`

**Interfaces:**
- Consumes: the `devices` manifest (T440).
- Produces: the same component under the new path, file name `DevicesView.vue`.

- [ ] **Step 1: Write the failing test**: `it('the devices route loads the view from the module [T443]')` (as in T441, for `DevicesView`).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/modules/devices/views/DevicesView.moved.test.js`. Expected: FAIL (the view is still in `src/views/`).
- [ ] **Step 3: Move** with `git mv`; change only relative paths in the view and its two tests; change the manifest line.
- [ ] **Step 4: Run.** Run: `cd bee-with-me\frontend; npm test -- src/modules src/architecture.test.js; npm run build`. Expected: PASS and a clean build.
- [ ] **Step 5: Commit** `refactor(devices): T443 move DevicesView into the devices module`.

dod:
- `cd bee-with-me\frontend; npm test -- src/modules src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`

### B78: `UsersView` keeps a stale load error after a successful reload

**risk:** low
**owner:** frontend-designer
**Files:**
- Modify: `frontend/src/modules/people/views/UsersView.vue` (`load`)
- Test: `frontend/src/modules/people/views/UsersView.b78.test.js`
- Modify: `docs/superpowers/plans/2026-10-31-vs-phase0-1.bugs.md` (the B78 status line only)

**Interfaces:**
- Consumes: the moved view (T441).
- Produces: `load()` clears `pageError` only when the request succeeded (set it to `''` after the awaited `Promise.all`, before the rows are assigned), so a failed reload keeps its message and a successful one removes the old message without a flash. This deviates from the wording of the bug entry ("reset `pageError` at the start of `load()`"): clearing at the start would blank the message while a retry is still running and flash it back on a second failure. The observable requirement of the entry and its DoD (the error is gone after a successful reload) is met; say so in the PR body.

- [ ] **Step 1: Write the failing tests** with the mock set-up of `UsersView.b69.test.js` (copied): `it('a successful reload removes the old load error [B78]')` (`getUsers` rejects once, the page shows `.page-error`; `getUsers` then resolves `{ items: [], total: 0 }` and the page is reloaded with `await wrapper.vm.goToPage(0)` (the pagination buttons are rendered only when `total > limit`, which is not the case after a failed first load); `.page-error` no longer exists); `it('a failed reload keeps the rows and shows the error [B78]')` (first load resolves one user, second rejects: the row is still rendered and `.page-error` shows the text of `users.loadError`).
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- -t "B78"`. Expected: FAIL (the first test still finds `.page-error`).
- [ ] **Step 3: Fix** `load()` as described.
- [ ] **Step 4: Run.** Run: `cd bee-with-me\frontend; npm test -- src/modules/people; npm run build`. Expected: PASS and a clean build.
- [ ] **Step 5: Commit** `fix(people): B78 a successful reload clears the old load error`, then set `**status:** fixed (<sha>)` on B78 in the bugs file in a second commit.

dod:
- `cd bee-with-me\frontend; npm test -- -t "B78"`
- `cd bee-with-me\frontend; npm test -- src/modules/people`

### B77: the first `load()` of `GroupsView` and `DevicesView` is unguarded

**risk:** normal
**owner:** frontend-designer
**Files:**
- Modify: `frontend/src/modules/teams/views/GroupsView.vue` (`load`, `selectGroup`, the member add and remove paths that await without a `catch`)
- Modify: `frontend/src/modules/devices/views/DevicesView.vue` (`load`)
- Modify: `frontend/src/modules/teams/i18n/en.js`, `bg.js` (`groups.loadError`), `frontend/src/modules/devices/i18n/en.js`, `bg.js` (`devices.loadError`)
- Test: `frontend/src/modules/teams/views/GroupsView.b77.test.js`, `frontend/src/modules/devices/views/DevicesView.b77.test.js`
- Modify: `docs/superpowers/plans/2026-10-31-vs-phase0-1.bugs.md` (the B77 status line only)

**Interfaces:**
- Consumes: the moved views (T442, T443); `errorText(e, fallback)` from `api/client.js` (as `UsersView.load` uses it).
- Produces: in both views `load()` wraps its requests in `try`/`catch`, sets `pageError.value = errorText(e, t('<ns>.loadError'))` on failure, clears `pageError` after a successful load, and keeps the rows already shown when a reload fails. `GroupsView.selectGroup` does the same with `groups.loadError` and leaves `selected` as it was. Texts: `groups.loadError` = `Could not load the teams. Check the connection and try again.` / `Екипите не можаха да се заредят. Проверете връзката и опитайте отново.`; `devices.loadError` = `Could not load the devices. Check the connection and try again.` / `Устройствата не можаха да се заредят. Проверете връзката и опитайте отново.` (the wording follows `users.loadError`; read it first and match its tone in both languages).

- [ ] **Step 1: Read, then write the failing tests.** Read `GroupsView.vue` from `load` to the last member handler and list every `await` that has no `catch`; each gets a test. Tests with the mock set-ups of `GroupsView.b70.test.js` and `DevicesView.b70.test.js` (copied), each `[B77]`, each registering a `process.on('unhandledRejection', ...)` listener that fails the test if it fires: `a rejected first load shows the load error in the page language` (for `getGroups`, for `getUsers` inside the groups load, for `getDevices`; English and Bulgarian text); `a rejected getGroup shows the load error and keeps the previous selection`; `a load that succeeds after a failure removes the error`; `a failed reload keeps the rows already shown`; one test per unguarded member path found in the reading, asserting the error element and no unhandled rejection.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- -t "B77"`. Expected: FAIL (unhandled rejection, no `.page-error`).
- [ ] **Step 3: Fix** the two views and add the two keys in both languages (the parity test of plan 1 fails if one language is missing).
- [ ] **Step 4: Run.** Run: `cd bee-with-me\frontend; npm test -- src/modules; npm run build`. Expected: PASS and a clean build.
- [ ] **Step 5: Commit** `fix(teams,devices): B77 guard the first load and the group selection`, then set `**status:** fixed (<sha>)` on B77 in the bugs file in a second commit.

dod:
- `cd bee-with-me\frontend; npm test -- -t "B77"`
- `cd bee-with-me\frontend; npm test -- src/modules`
- `cd bee-with-me\frontend; npm run build`

### Task 444: stores of `people`, `teams` and `devices`

**risk:** normal
**owner:** implementer
**Files:**
- Create: `frontend/src/modules/people/store.js`, `frontend/src/modules/teams/store.js`, `frontend/src/modules/devices/store.js`
- Test: `frontend/src/modules/people/store.test.js`, `frontend/src/modules/teams/store.test.js`, `frontend/src/modules/devices/store.test.js`

**Interfaces:**
- Consumes: `getUsers`, `getGroupsWithMembers`, `getDevices` from `src/api/index.js` (unchanged); `normaliseGroups` is not needed (the member list arrives decoded).
- Produces three Pinia setup stores with one shape:
  - `usePeopleStore` (id `people`): `items` (array), `byId` (computed object keyed by `id`), `loaded` (boolean), `failed` (boolean), `truncated` (boolean), `load()`.
  - `useTeamsStore` (id `teams`): the same names; `items` are teams with their `members`.
  - `useDevicesStore` (id `devices`): the same names plus `repeaters` (computed: `items` whose `device_type === 'repeater'`); `truncated` is always `false` (the endpoint is not paged).
  - `load()`: people call `getUsers({ limit: 500 })`, teams call `getGroupsWithMembers({ limit: 500 })`, devices call `getDevices()`. On success: `items` is replaced, `loaded = true`, `failed = false`, `truncated = total > items.length` for the two paged lists. On failure: `failed = true`, `items` and `loaded` keep their values, and the promise rejects with the same error so a caller can show it. Only the answer of the latest `load()` call is applied (a sequence counter; an older answer that arrives later is dropped, and its rejection is not turned into `failed`).
- The stores hold personal data in memory only: nothing is written to `localStorage` or logged (DP-02).
- No view, composable or other store imports them in this wave.

- [ ] **Step 1: Write the failing tests** with `vi.mock('../../api', ...)`, each `[T444]`, for each store: `load fills items and byId and sets loaded`; `a failed load keeps the previous items, sets failed and rejects`; `a later success clears failed`; `truncated is true when total exceeds the returned rows` (people and teams: `{ items: [one], total: 2 }`); `the latest load wins when answers arrive out of order` (first call resolves after the second with other rows: the rows of the second call stay); `nothing is written to localStorage` (`localStorage.length === 0` after a load); for devices also `repeaters lists only repeaters`.
- [ ] **Step 2: Run, expect FAIL.** Run: `cd bee-with-me\frontend; npm test -- src/modules/people/store.test.js src/modules/teams/store.test.js src/modules/devices/store.test.js`. Expected: FAIL (`Failed to resolve import "./store.js"`).
- [ ] **Step 3: Implement** the three stores (setup style, like `stores/settings.js`).
- [ ] **Step 4: Run** the stores and the architecture rules (`lib-is-pure` for module `lib/`, no cycle). Run: `cd bee-with-me\frontend; npm test -- src/modules src/architecture.test.js; npm run build`. Expected: PASS and a clean build.
- [ ] **Step 5: Commit** `feat(modules): T444 stores for people, teams and devices`.

dod:
- `cd bee-with-me\frontend; npm test -- src/modules src/architecture.test.js`
- `cd bee-with-me\frontend; npm run build`
