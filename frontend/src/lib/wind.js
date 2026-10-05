// Wind field helpers for the map's wind layer (MapView.vue).
//
// Directions are meteorological: `deg` is where the wind blows FROM, clockwise from north
// (270 = a westerly, blowing towards the east). Screen vectors point where it blows TO.

const COMPASS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']

/** 8-point compass name of the direction the wind comes from, or '' when unknown. */
export function compassFrom(deg) {
  if (deg == null || !Number.isFinite(deg)) return ''
  return COMPASS[Math.round((((deg % 360) + 360) % 360) / 45) % 8]
}

/** Unit screen vector (x right, y down) the wind blows towards, for a "from" direction. */
export function downwindUnit(deg) {
  const rad = (deg ?? 0) * Math.PI / 180
  return { x: -Math.sin(rad), y: Math.cos(rad) }
}

/** A wind sample as the field uses it. */
export function windPoint(lat, lon, deg, speed) {
  const u = downwindUnit(deg)
  return { lat, lon, deg, speed, vxNorm: u.x, vyNorm: u.y }
}

/** cols × rows sample points spread evenly over a lon/lat box (cell centres). */
export function gridPoints(minLon, minLat, maxLon, maxLat, cols, rows) {
  const pts = []
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      pts.push({
        lat: minLat + (r + 0.5) * (maxLat - minLat) / rows,
        lon: minLon + (c + 0.5) * (maxLon - minLon) / cols,
      })
    }
  }
  return pts
}

/**
 * Open-Meteo current-wind URL for several points in one request (keyless, free tier).
 * Coordinates are rounded to 0.01° (about 1 km): enough for a grid cell, and it keeps the URL short.
 */
export function openMeteoUrl(points) {
  const lat = points.map(p => p.lat.toFixed(2)).join(',')
  const lon = points.map(p => p.lon.toFixed(2)).join(',')
  return 'https://api.open-meteo.com/v1/forecast'
    + `?latitude=${lat}&longitude=${lon}`
    + '&current=wind_speed_10m,wind_direction_10m,wind_gusts_10m&wind_speed_unit=ms'
}

/**
 * Wind points from an Open-Meteo response: an array for several locations, a single object for one.
 * Entries without a usable speed and direction are left out.
 */
export function parseOpenMeteo(body) {
  const list = Array.isArray(body) ? body : body ? [body] : []
  const out = []
  for (const loc of list) {
    const cur = loc?.current
    const speed = cur?.wind_speed_10m
    const deg = cur?.wind_direction_10m
    if (!Number.isFinite(loc?.latitude) || !Number.isFinite(loc?.longitude)) continue
    if (!Number.isFinite(speed) || !Number.isFinite(deg)) continue
    const p = windPoint(loc.latitude, loc.longitude, deg, speed)
    p.gust = Number.isFinite(cur.wind_gusts_10m) ? cur.wind_gusts_10m : null
    out.push(p)
  }
  return out
}

/** The point closest to lon/lat (plain degree distance: fine for picking the panel's reading). */
export function nearestPoint(points, lon, lat) {
  let best = null, bestD = Infinity
  for (const p of points) {
    const d = (p.lon - lon) ** 2 + (p.lat - lat) ** 2
    if (d < bestD) { bestD = d; best = p }
  }
  return best
}
