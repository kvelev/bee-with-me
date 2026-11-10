// The map's layer stacking order, kept in one place (values are the ones useMap.js used before the
// map shell). A module declares its layer's zIndex in its manifest; features that have no module
// yet take theirs from this table.
export const Z = Object.freeze({
  weather: 2,
  burnt: 3,
  zones: 3.4,
  hotspots: 3.5,
  graticule: 4,
  trail: 5,
  checkpoints: 6,
  trackers: 10,
  repeaters: 14,
  hq: 15,
  measure: 20,
})

// Banner priority: lower is shown first. Only the id `sos` may sit at or below BANNER_PRIORITY.sos (BP-02).
export const BANNER_PRIORITY = Object.freeze({ sos: 10, fireAlarm: 20 })
