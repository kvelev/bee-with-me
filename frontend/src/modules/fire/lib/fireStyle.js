// Pure classification for fire features and feed freshness. The map layer turns these keys
// into OpenLayers styles, the freshness pill turns them into words; neither lives here.

const HOUR_MS = 3600 * 1000

// The backend polls EFFIS every 30 min. Past three missed cycles the "as of" time is itself
// old news, whatever upstream_state last said.
export const FIRE_DATA_STALE_MS = 90 * 60 * 1000

export function hotspotStyleKey(props, nowMs = Date.now()) {
  if (props.state === 'dismissed')    return 'dismissed'
  if (props.state === 'extinguished') return 'extinguished'
  if (props.state === 'suppressed')   return 'suppressed'
  if (props.source === 'field_report') return 'field_report'
  const age = nowMs - Date.parse(props.acquired_at)
  // A future or unparseable time must not hide a detection: show it as the freshest.
  if (!Number.isFinite(age) || age <= 24 * HOUR_MS) return 'age_24h'
  if (age <= 72 * HOUR_MS) return 'age_3d'
  return 'age_7d'
}

export function freshnessKind(upstreamState) {
  if (upstreamState === 'live') return 'live'
  if (upstreamState === 'no_recent_detections') return 'quiet'
  if (upstreamState === 'error') return 'error'
  return 'unknown'
}

/** True when the feed's last success is older than the poll cycle can explain.
 *  null / unparseable counts as "never fetched", which the pill shows separately. */
export function isFireDataStale(fetchedAt, nowMs = Date.now()) {
  const t = Date.parse(fetchedAt)
  if (!Number.isFinite(t)) return false
  return nowMs - t > FIRE_DATA_STALE_MS
}

const SEVERITY = { live: 0, quiet: 1, unknown: 2, error: 3 }

/** Worst of several upstream states, so two feeds never average into a reassuring one. */
export function worstUpstreamState(states) {
  let worst = null
  for (const s of states) {
    if (worst === null || SEVERITY[freshnessKind(s)] > SEVERITY[freshnessKind(worst)]) worst = s
  }
  return worst ?? 'unknown'
}

/** Oldest of several as-of times; null if any feed has never been fetched. */
export function oldestFetchedAt(times) {
  if (!times.length || times.some(t => !Number.isFinite(Date.parse(t)))) return null
  return times.reduce((a, b) => (Date.parse(a) <= Date.parse(b) ? a : b))
}

/** What the fire freshness pill says, as data (the view turns it into words and a time).
 *  Order matters: a failure outranks everything, then never-fetched, then an as-of time
 *  too old to trust, then the quiet and live cases. A failure with no as-of time means
 *  nothing is on the map, so it must not claim "showing last known" (BP-01). */
export function firePillState({ at, upstreamState, failed, nowMs = Date.now() }) {
  const kind = freshnessKind(upstreamState)
  const hasAt = Number.isFinite(Date.parse(at))
  if (failed || kind === 'error') {
    return { kind: 'error', noteKey: hasAt ? 'fire.error' : 'fire.errorNoData' }
  }
  if (!hasAt) return { kind: 'unknown', noteKey: 'fire.neverFetched' }
  if (isFireDataStale(at, nowMs)) return { kind: 'error', noteKey: 'fire.stale' }
  if (kind === 'quiet') return { kind: 'quiet', noteKey: 'fire.quiet' }
  return { kind, noteKey: '' }
}
