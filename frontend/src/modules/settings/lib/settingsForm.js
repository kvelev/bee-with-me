// Pure helpers for the Settings page: validation and unit conversion (km <-> m),
// and the check that decides when saving needs an explicit confirmation (BP-02).

export const LIMITS = {
  km:      { min: 0.1, max: 100 },
  hours:   { min: 1,   max: 168 },
  minutes: { min: 1,   max: 60 },
}

export function parseNumber(raw) {
  if (raw === '' || raw === null || raw === undefined) return null
  const n = Number(raw)
  return Number.isFinite(n) ? n : null
}

export function kmError(raw) {
  const n = parseNumber(raw)
  return n === null || n < LIMITS.km.min || n > LIMITS.km.max ? 'errRangeKm' : null
}

export function wholeError(raw, { min, max }, key) {
  const n = parseNumber(raw)
  return n === null || !Number.isInteger(n) || n < min || n > max ? key : null
}

export const kmToM = (km) => Math.round(Number(km) * 1000)
export const mToKm = (m) => m / 1000

// The photo switch defaults to on: an older server response without the field means on.
export const photosOnMapOf = (s) => s?.is_rescuer_photo_on_map_enabled !== false

// Names of the alarms that are on in `current` and off in `draft`.
export function alarmsTurnedOff(current, draft) {
  const off = []
  if (current?.is_hq_alarm_enabled && !draft.is_hq_alarm_enabled) off.push('hq')
  if (current?.is_rescuer_alarm_enabled && !draft.is_rescuer_alarm_enabled) off.push('rescuer')
  return off
}
