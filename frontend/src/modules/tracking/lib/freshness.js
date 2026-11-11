/**
 * How old a position is, and what that means operationally.
 *
 * Freshness is always judged on `received_at` — the moment the server saw the frame —
 * never on `recorded_at`, which comes from the device's GNSS clock and can be skewed or
 * plain wrong. A tracker that looks fresh because its clock is fast is worse than useless.
 *
 * (Both are the same machine in the standard deployment, so browser-vs-server clock skew
 * is zero. If the map is ever opened from a second device, this needs a server-supplied
 * reference time rather than Date.now().)
 */

export const STALE_MS = 10 * 60 * 1000   // no contact for 10 min — attention
export const LOST_MS  = 30 * 60 * 1000   // no contact for 30 min — treat as lost contact

export const LIVE  = 'live'
export const STALE = 'stale'
export const LOST  = 'lost'

/** Server-clock timestamp for a position, in ms. Falls back to device time for rows
 *  written before received_at was carried through the live path. */
export function contactAt(pos) {
  const raw = pos?.received_at ?? pos?.recorded_at
  if (!raw) return null
  const t = new Date(raw).getTime()
  return Number.isNaN(t) ? null : t
}

export function ageMs(pos, now = Date.now()) {
  const t = contactAt(pos)
  return t == null ? null : Math.max(0, now - t)
}

export function freshnessOf(pos, now = Date.now()) {
  const age = ageMs(pos, now)
  if (age == null) return LIVE
  if (age > LOST_MS)  return LOST
  if (age > STALE_MS) return STALE
  return LIVE
}

/** Compact relative age for dense panel rows: 42s · 7m · 1h04 · 2d */
export function formatAge(ms) {
  if (ms == null) return '—'
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h${String(m % 60).padStart(2, '0')}`
  return `${Math.floor(h / 24)}d`
}

/** Sort worst-first: SOS, then lost contact, then stale, then by age descending.
 *  What needs attention rises to the top of the panel on its own. */
export function byUrgency(a, b, now = Date.now()) {
  if (!!a.sos_active !== !!b.sos_active) return a.sos_active ? -1 : 1
  const ageA = ageMs(a, now) ?? 0
  const ageB = ageMs(b, now) ?? 0
  return ageB - ageA
}
