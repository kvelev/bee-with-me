// Module manifest contract (Architecture/application/modular-monolith.md, sections 3.2 and 7).
// A frontend module's `index.js` default-exports one manifest; the map shell and router read the list of
// manifests and never name a module in code. Nothing imports this file yet (step 0 of the vertical-slice
// programme); `validateManifest` is the contract that later steps and the architecture test use.

import { PANEL_HOSTS } from './map-shell/contributions.js'

const NAME = /^[a-z][a-z0-9-]*$/
const LIVE_HOOKS = ['setup', 'onTick', 'onReconnect']

const isObject = (v) => v !== null && typeof v === 'object' && !Array.isArray(v)
const isText = (v) => typeof v === 'string' && v.trim() !== ''
const isComponent = (v) => typeof v === 'function' || isObject(v)

function listOf(m, field, itemCheck, problems) {
  const list = m[field]
  if (list === undefined) {
    problems.push(`${field}: missing (use [] when the module contributes none)`)
    return
  }
  if (!Array.isArray(list)) {
    problems.push(`${field}: must be an array`)
    return
  }
  list.forEach((item, i) => {
    for (const p of itemCheck(item)) problems.push(`${field}[${i}]: ${p}`)
  })
}

const routeProblems = (r) => !isObject(r) ? ['must be an object']
  : [
      ...(isText(r.path) && r.path.startsWith('/') ? [] : ['path must be a string starting with "/"']),
      ...(isText(r.name) ? [] : ['name must be a non-empty string']),
      ...(isComponent(r.component) ? [] : ['component must be a component or a lazy import function']),
    ]

const navProblems = (n) => !isObject(n) ? ['must be an object']
  : [
      ...(isText(n.to) ? [] : ['to must be a non-empty string']),
      ...(isText(n.labelKey) ? [] : ['labelKey must be an i18n key']),
    ]

// `isOn` and `set` drive the layer's state from the module; both or neither.
const stateHookProblems = (t) => {
  if (t.isOn === undefined && t.set === undefined) return []
  if (t.isOn === undefined || t.set === undefined) return ['toggle.isOn and toggle.set must be given together']
  return [
    ...(typeof t.isOn === 'function' ? [] : ['toggle.isOn must be a function']),
    ...(typeof t.set === 'function' ? [] : ['toggle.set must be a function']),
  ]
}

const toggleProblems = (t) => !isObject(t) ? ['toggle must be an object']
  : [
      ...(isText(t.labelKey) ? [] : ['toggle.labelKey must be an i18n key']),
      ...(Number.isFinite(t.order) ? [] : ['toggle.order must be a finite number']),
      ...(t.adminOnly === undefined || typeof t.adminOnly === 'boolean' ? [] : ['toggle.adminOnly must be a boolean']),
      ...(t.key === undefined || isText(t.key) ? [] : ['toggle.key must be a non-empty string']),
      ...stateHookProblems(t),
    ]

const layerProblems = (l) => !isObject(l) ? ['must be an object']
  : [
      ...(isText(l.id) ? [] : ['id must be a non-empty string']),
      ...(Number.isFinite(l.zIndex) ? [] : ['zIndex must be a finite number']),
      ...(l.toggle === undefined ? [] : toggleProblems(l.toggle)),
      ...(l.create === undefined ? [] : ['create: map code belongs in map/index.js, not in the manifest']),
    ]

const panelProblems = (p) => !isObject(p) ? ['must be an object']
  : [
      ...(isText(p.id) ? [] : ['id must be a non-empty string']),
      ...(isComponent(p.component) ? [] : ['component must be a component']),
      ...(p.host === undefined || PANEL_HOSTS.includes(p.host) ? [] : [`host must be one of ${PANEL_HOSTS.join(', ')}`]),
      ...(p.order === undefined || Number.isFinite(p.order) ? [] : ['order must be a finite number']),
      ...(p.retryKey === undefined || typeof p.retryKey === 'function' ? [] : ['retryKey must be a function']),
    ]

const bannerProblems = (b) => !isObject(b) ? ['must be an object']
  : [
      ...(isText(b.id) ? [] : ['id must be a non-empty string']),
      ...(Number.isFinite(b.priority) ? [] : ['priority must be a finite number (lower is shown first)']),
      ...(isComponent(b.component) ? [] : ['component must be a component']),
    ]

const popupProblems = (p) => !isObject(p) ? ['must be an object']
  : [
      ...(isText(p.id) ? [] : ['id must be a non-empty string']),
      ...(isComponent(p.component) ? [] : ['component must be a component']),
      ...(Array.isArray(p.kinds) && p.kinds.length > 0 && p.kinds.every(isText) ? [] : ['kinds must be a non-empty array of strings']),
    ]

const contextMenuProblems = (c) => !isObject(c) ? ['must be an object']
  : [
      ...(isText(c.id) ? [] : ['id must be a non-empty string']),
      ...(Number.isFinite(c.order) ? [] : ['order must be a finite number']),
      ...(isText(c.labelKey) ? [] : ['labelKey must be an i18n key']),
      ...(typeof c.onSelect === 'function' ? [] : ['onSelect must be a function']),
    ]

// Like listOf, but the field may be absent.
function optionalListOf(m, field, itemCheck, problems) {
  if (m[field] === undefined) return
  listOf(m, field, itemCheck, problems)
}

const dependsProblems = (d) => (isText(d) && NAME.test(d) ? [] : ['must be a module name'])

/**
 * Check a module manifest. Returns one message per problem; an empty array means the manifest is valid.
 * Required fields: name, routes, nav, mapLayers, panels, banners, liveHandlers, i18n ({en, bg}), depends.
 * Optional fields (checked only when present): popups, contextMenu, live ({setup, onTick, onReconnect} functions),
 * and `toggle` on a mapLayers item.
 */
export function validateManifest(m) {
  if (!isObject(m)) return ['manifest: must be an object']
  const problems = []

  if (!isText(m.name)) problems.push('name: missing or not a non-empty string')
  else if (!NAME.test(m.name)) problems.push('name: must be lowercase letters, digits and "-", starting with a letter')

  listOf(m, 'routes', routeProblems, problems)
  listOf(m, 'nav', navProblems, problems)
  listOf(m, 'mapLayers', layerProblems, problems)
  listOf(m, 'panels', panelProblems, problems)
  listOf(m, 'banners', bannerProblems, problems)
  listOf(m, 'depends', dependsProblems, problems)
  optionalListOf(m, 'popups', popupProblems, problems)
  optionalListOf(m, 'contextMenu', contextMenuProblems, problems)
  if (m.live !== undefined) {
    if (!isObject(m.live)) problems.push('live: must be an object with setup, onTick or onReconnect functions')
    else {
      for (const [key, fn] of Object.entries(m.live)) {
        if (!LIVE_HOOKS.includes(key)) problems.push(`live.${key}: unknown hook (use ${LIVE_HOOKS.join(', ')})`)
        else if (typeof fn !== 'function') problems.push(`live.${key}: must be a function`)
      }
    }
  }
  if (m.mapSetup !== undefined) problems.push('mapSetup: map code belongs in map/index.js, not in the manifest')

  if (m.liveHandlers === undefined) problems.push('liveHandlers: missing (use {} when the module has no live data)')
  else if (!isObject(m.liveHandlers)) problems.push('liveHandlers: must be an object of message type to handler')
  else {
    for (const [type, fn] of Object.entries(m.liveHandlers)) {
      if (typeof fn !== 'function') problems.push(`liveHandlers.${type}: must be a function`)
    }
  }

  if (m.i18n === undefined) problems.push('i18n: missing (needs {en, bg})')
  else if (!isObject(m.i18n)) problems.push('i18n: must be an object with en and bg')
  else {
    for (const lang of ['en', 'bg']) {
      if (!isObject(m.i18n[lang])) problems.push(`i18n.${lang}: missing or not an object`)
    }
  }

  return problems
}
