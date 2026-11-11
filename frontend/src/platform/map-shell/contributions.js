// Pure collectors for the map shell's contribution points. They merge the manifests of the modules
// with "legacy entries" (items of the same shape for features that have no module yet) and sort them.
// Each collector takes (modules, legacy = []); `legacy` is a list of items of that one kind.
// `contributionProblems` checks all kinds at once, so its `legacy` is an object
// { banners, mapLayers, panels, popups, contextMenu } (each optional).
import { BANNER_PRIORITY } from './zorder.js'

const SOS_ID = 'sos'

// Where a module panel may be mounted (`PanelHost` tags in MapView.vue and the settings view).
export const PANEL_HOSTS = ['map-root', 'map', 'map-toolbar', 'settings']
const DEFAULT_PANEL_ORDER = 100

const fromModules = (modules, field) =>
  (Array.isArray(modules) ? modules : []).flatMap((m) => (m && Array.isArray(m[field]) ? m[field] : []))

const isItem = (x) => x !== null && typeof x === 'object'

const gather = (modules, field, legacy) => [
  ...fromModules(modules, field),
  ...(Array.isArray(legacy) ? legacy : []),
].filter(isItem)

// Total order: finite numbers ascending, non-finite or missing keys last, ties by plain id compare.
const finite = (n) => typeof n === 'number' && Number.isFinite(n)
const byNumberThenId = (key) => (a, b) => {
  const fa = finite(a[key])
  const fb = finite(b[key])
  if (fa !== fb) return fa ? -1 : 1
  if (fa && a[key] !== b[key]) return a[key] < b[key] ? -1 : 1
  const ia = String(a.id)
  const ib = String(b.id)
  return ia < ib ? -1 : ia > ib ? 1 : 0
}

export function collectBanners(modules, legacy = []) {
  return gather(modules, 'banners', legacy).sort(byNumberThenId('priority'))
}

export function collectMapLayers(modules, legacy = []) {
  return gather(modules, 'mapLayers', legacy).sort(byNumberThenId('zIndex'))
}

export function collectLayerToggles(modules, legacy = []) {
  return collectMapLayers(modules, legacy)
    .filter((l) => l.toggle)
    .map((l) => ({
      id: l.id,
      labelKey: l.toggle.labelKey,
      order: l.toggle.order,
      adminOnly: l.toggle.adminOnly === true,
      key: l.toggle.key,
      isOn: l.toggle.isOn,
      set: l.toggle.set,
    }))
    .sort(byNumberThenId('order'))
}

// Panels of one host, by `order` (default 100), then id. A panel without a known host is in no list.
export function collectPanels(modules, host, legacy = []) {
  const order = (p) => (finite(p.order) ? p.order : DEFAULT_PANEL_ORDER)
  return gather(modules, 'panels', legacy)
    .filter((p) => p.host === host && PANEL_HOSTS.includes(host))
    .sort((a, b) => (order(a) - order(b)) || (String(a.id) < String(b.id) ? -1 : String(a.id) > String(b.id) ? 1 : 0))
}

export function collectPopups(modules, legacy = []) {
  return gather(modules, 'popups', legacy)
}

export function popupFor(popups, kind) {
  return (Array.isArray(popups) ? popups : []).find((p) => isItem(p) && Array.isArray(p.kinds) && p.kinds.includes(kind)) || null
}

export function collectContextMenu(modules, legacy = []) {
  return gather(modules, 'contextMenu', legacy).sort(byNumberThenId('order'))
}

/** Cross-module checks the single-manifest validator cannot do. One message per problem; [] is clean. */
export function contributionProblems(modules, legacy = {}) {
  if (Array.isArray(legacy) || (legacy !== undefined && legacy !== null && typeof legacy !== 'object')) {
    throw new TypeError('contributionProblems: legacy must be { banners, mapLayers, panels, popups, contextMenu }')
  }
  const extra = legacy || {}
  const problems = []

  const lists = {
    banners: gather(modules, 'banners', extra.banners),
    mapLayers: gather(modules, 'mapLayers', extra.mapLayers),
    panels: gather(modules, 'panels', extra.panels),
    popups: gather(modules, 'popups', extra.popups),
    contextMenu: gather(modules, 'contextMenu', extra.contextMenu),
  }

  for (const [kind, items] of Object.entries(lists)) {
    const seen = new Set()
    const reported = new Set()
    for (const item of items) {
      if (seen.has(item.id) && !reported.has(item.id)) {
        problems.push(`${kind}: id "${item.id}" is used more than once`)
        reported.add(item.id)
      }
      seen.add(item.id)
    }
  }

  const byPriority = new Map()
  for (const b of lists.banners) {
    if (!byPriority.has(b.priority)) byPriority.set(b.priority, [])
    byPriority.get(b.priority).push(b.id)
    if (b.id === SOS_ID) {
      if (b.priority !== BANNER_PRIORITY.sos) {
        problems.push(`banners: "${SOS_ID}" must have priority ${BANNER_PRIORITY.sos}, has ${b.priority}`)
      }
    } else if (!(b.priority > BANNER_PRIORITY.sos)) {
      problems.push(`banners: "${b.id}" has priority ${b.priority}; only "${SOS_ID}" may sit at ${BANNER_PRIORITY.sos} or less`)
    }
  }
  for (const [priority, bannerIds] of byPriority) {
    if (bannerIds.length > 1) {
      problems.push(`banners: ${bannerIds.map((i) => `"${i}"`).join(' and ')} share priority ${priority}`)
    }
  }

  const claimedBy = new Map()
  for (const p of lists.popups) {
    for (const kind of Array.isArray(p.kinds) ? p.kinds : []) {
      if (claimedBy.has(kind) && claimedBy.get(kind) !== p.id) {
        problems.push(`popups: kind "${kind}" is claimed by "${claimedBy.get(kind)}" and "${p.id}"`)
      } else {
        claimedBy.set(kind, p.id)
      }
    }
  }

  return problems
}
