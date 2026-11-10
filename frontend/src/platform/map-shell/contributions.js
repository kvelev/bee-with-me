// Pure collectors for the map shell's contribution points. They merge the manifests of the modules
// with "legacy entries" (items of the same shape for features that have no module yet) and sort them.
// Each collector takes (modules, legacy = []); `legacy` is a list of items of that one kind.
// `contributionProblems` checks all kinds at once, so its `legacy` is an object
// { banners, mapLayers, popups, contextMenu } (each optional).
import { BANNER_PRIORITY } from './zorder.js'

const SOS_ID = 'sos'

const fromModules = (modules, field) =>
  (Array.isArray(modules) ? modules : []).flatMap((m) => (m && Array.isArray(m[field]) ? m[field] : []))

const gather = (modules, field, legacy) => [
  ...fromModules(modules, field),
  ...(Array.isArray(legacy) ? legacy : []),
]

const byNumberThenId = (key) => (a, b) => (a[key] - b[key]) || String(a.id).localeCompare(String(b.id))

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
    }))
    .sort(byNumberThenId('order'))
}

export function collectPopups(modules, legacy = []) {
  return gather(modules, 'popups', legacy)
}

export function popupFor(popups, kind) {
  return (Array.isArray(popups) ? popups : []).find((p) => Array.isArray(p.kinds) && p.kinds.includes(kind)) || null
}

export function collectContextMenu(modules, legacy = []) {
  return gather(modules, 'contextMenu', legacy).sort(byNumberThenId('order'))
}

/** Cross-module checks the single-manifest validator cannot do. One message per problem; [] is clean. */
export function contributionProblems(modules, legacy = {}) {
  const extra = legacy && !Array.isArray(legacy) ? legacy : {}
  const problems = []

  const lists = {
    banners: gather(modules, 'banners', extra.banners),
    mapLayers: gather(modules, 'mapLayers', extra.mapLayers),
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
