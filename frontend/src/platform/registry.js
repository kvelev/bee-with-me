// Module registry (T403): pure helpers that turn the list of module manifests into routes, navigation and i18n.
// Imports only the manifest contract; the list itself (src/modules/index.js) is passed in by the callers, so the
// platform never names a module (rule `platform-imports-no-module`).
import { validateManifest } from './manifest.js'

const isPlainObject = (v) => v !== null && typeof v === 'object' && !Array.isArray(v)

/** Problems of the whole list. Empty array means the list is valid. */
export function checkModules(modules) {
  const problems = []
  const names = new Set()
  const routeNames = new Set()
  const routePaths = new Set()
  const navTargets = new Set()

  modules.forEach((m, i) => {
    const label = isPlainObject(m) && typeof m.name === 'string' && m.name !== '' ? m.name : `module[${i}]`
    for (const p of validateManifest(m)) problems.push(`${label}: ${p}`)
    if (!isPlainObject(m)) return

    if (typeof m.name === 'string') {
      if (names.has(m.name)) problems.push(`${label}: duplicate module name: ${m.name}`)
      names.add(m.name)
    }
    for (const r of Array.isArray(m.routes) ? m.routes : []) {
      if (!isPlainObject(r)) continue
      if (routeNames.has(r.name)) problems.push(`${label}: duplicate route name: ${r.name}`)
      routeNames.add(r.name)
      if (routePaths.has(r.path)) problems.push(`${label}: duplicate route path: ${r.path}`)
      routePaths.add(r.path)
    }
    for (const n of Array.isArray(m.nav) ? m.nav : []) {
      if (!isPlainObject(n)) continue
      if (navTargets.has(n.to)) problems.push(`${label}: duplicate navigation target: ${n.to}`)
      navTargets.add(n.to)
      if (!Number.isFinite(n.order)) problems.push(`${label}: nav ${n.to}: order must be a finite number`)
    }
  })
  return problems
}

/** All routes of all modules, in list order. */
export function collectRoutes(modules) {
  return modules.flatMap((m) => m.routes ?? [])
}

/** Static and module navigation items sorted by `order` (Array.prototype.sort is stable). */
export function collectNav(staticItems, modules) {
  return [...staticItems, ...modules.flatMap((m) => m.nav ?? [])].sort((a, b) => a.order - b.order)
}

function mergeInto(target, source) {
  for (const [key, value] of Object.entries(source)) {
    if (isPlainObject(value)) {
      if (!Object.hasOwn(target, key)) target[key] = {}
      if (isPlainObject(target[key])) mergeInto(target[key], value)
      // a leaf already stands where a namespace is wanted: the first value stays
    } else if (!Object.hasOwn(target, key)) {
      target[key] = value
    }
  }
}

/** Deep merge: `core` first, then the dictionaries in order. The first value of a leaf stays. Inputs are not changed. */
export function mergeMessages(core, dictionaries) {
  const merged = {}
  for (const source of [core, ...dictionaries]) mergeInto(merged, source)
  return merged
}

/** Dotted keys of all leaves (anything that is not a plain object), sorted. */
export function leafKeys(dictionary, prefix = '') {
  const keys = Object.entries(dictionary).flatMap(([k, v]) =>
    isPlainObject(v) ? leafKeys(v, `${prefix}${k}.`) : [`${prefix}${k}`])
  return prefix === '' ? keys.sort() : keys
}

/** Dotted keys defined by more than one source (the core counts as a source). */
export function messageCollisions(core, dictionaries) {
  const seen = new Set()
  const twice = new Set()
  for (const source of [core, ...dictionaries]) {
    for (const key of leafKeys(source)) {
      if (seen.has(key)) twice.add(key)
      seen.add(key)
    }
  }
  return [...twice].sort()
}
