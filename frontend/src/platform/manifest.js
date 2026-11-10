// Module manifest contract (Architecture/application/modular-monolith.md, sections 3.2 and 7).
// A frontend module's `index.js` default-exports one manifest; the map shell and router read the list of
// manifests and never name a module in code. Nothing imports this file yet (step 0 of the vertical-slice
// programme); `validateManifest` is the contract that later steps and the architecture test use.

const NAME = /^[a-z][a-z0-9-]*$/

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

const layerProblems = (l) => !isObject(l) ? ['must be an object']
  : [
      ...(isText(l.id) ? [] : ['id must be a non-empty string']),
      ...(Number.isFinite(l.zIndex) ? [] : ['zIndex must be a finite number']),
    ]

const panelProblems = (p) => !isObject(p) ? ['must be an object']
  : [
      ...(isText(p.id) ? [] : ['id must be a non-empty string']),
      ...(isComponent(p.component) ? [] : ['component must be a component']),
    ]

const bannerProblems = (b) => !isObject(b) ? ['must be an object']
  : [
      ...(isText(b.id) ? [] : ['id must be a non-empty string']),
      ...(Number.isFinite(b.priority) ? [] : ['priority must be a finite number (lower is shown first)']),
      ...(isComponent(b.component) ? [] : ['component must be a component']),
    ]

const dependsProblems = (d) => (isText(d) && NAME.test(d) ? [] : ['must be a module name'])

/**
 * Check a module manifest. Returns one message per problem; an empty array means the manifest is valid.
 * Fields: name, routes, nav, mapLayers, panels, banners, liveHandlers, i18n ({en, bg}), depends.
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
