// Recolouring of OpenWeatherMap 1.0 weather tiles (clouds_new, precipitation_new, temp_new).
//
// OWM paints these layers very faintly: rain is a grey-blue at a few percent opacity and clouds a
// half-transparent near-white, which all but vanishes on the satellite basemap (the only one that
// offers weather layers). The tiles follow OWM's documented palettes, in which the colour, not
// only the opacity, tracks the value:
//   precipitation_new  blue channel  150 (0.1 mm/h) … 255 (140 mm/h)
//   clouds_new         red channel   253 (10 %)     … 240 (100 %)
//   temp_new           a colour ramp purple (−40 °C) … cyan (0) … yellow (20) … orange (30), painted
//                      over the whole map at a flat 30 % opacity
// So each pixel is decoded back to a value and repainted on a clear scale that the legend in
// MapView.vue (WEATHER_LAYERS) shows as is.

// [channel value, physical value] pairs from OWM's palettes, in channel order.
const PRECIP_BLUE_MM = [[150, 0.1], [170, 0.2], [190, 0.5], [205, 1], [225, 10], [255, 140]]
const CLOUD_RED_PCT  = [[240, 100], [242, 90], [243, 80], [244, 70], [246, 60], [247, 50], [249, 40], [250, 30], [252, 20], [253, 10], [255, 0]]

function interp(stops, x) {
  if (x <= stops[0][0]) return stops[0][1]
  for (let i = 1; i < stops.length; i++) {
    const [x1, y1] = stops[i]
    if (x <= x1) {
      const [x0, y0] = stops[i - 1]
      return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    }
  }
  return stops[stops.length - 1][1]
}

/** mm/h for an OWM precipitation pixel; 0 for a transparent one. */
export function precipMm(r, g, b, a) {
  return a === 0 ? 0 : interp(PRECIP_BLUE_MM, b)
}

/** Cloud cover in percent for an OWM clouds pixel; 0 for a transparent one. */
export function cloudPct(r, g, b, a) {
  return a === 0 ? 0 : interp(CLOUD_RED_PCT, r)
}

// Output scales. Rain: light blue → royal blue → deep blue → violet at 0.1 / 1 / 5 / 20 mm/h,
// never transparent enough to miss (drizzle is still 55 % opaque). No red, green or orange: those
// belong to SOS, fire and the stale warning on this map.
const RAIN_SCALE = [
  [0.1, [160, 216, 239], 0.55],
  [1,   [65, 105, 225],  0.75],
  [5,   [0, 0, 205],     0.85],
  [20,  [102, 0, 204],   0.9],
]
// Clouds: white, opacity rising with cover. Under 10 % is dropped so thin haze does not veil the map;
// 10–20 % fades in rather than starting at a step, which drew hard-edged blocks along OWM's grid.
const CLOUD_MIN_PCT  = 10
const CLOUD_FULL_PCT = 20
const CLOUD_RGB = [244, 247, 252]

function cloudAlpha(pct) {
  if (pct < CLOUD_MIN_PCT) return 0
  if (pct < CLOUD_FULL_PCT) return 0.2 * (pct - CLOUD_MIN_PCT) / (CLOUD_FULL_PCT - CLOUD_MIN_PCT)
  return 0.2 + 0.6 * (pct - CLOUD_FULL_PCT) / (100 - CLOUD_FULL_PCT)
}

function rainColour(mm) {
  if (mm <= RAIN_SCALE[0][0]) return [...RAIN_SCALE[0][1], RAIN_SCALE[0][2]]
  for (let i = 1; i < RAIN_SCALE.length; i++) {
    const [m1, c1, a1] = RAIN_SCALE[i]
    if (mm <= m1) {
      const [m0, c0, a0] = RAIN_SCALE[i - 1]
      const t = (mm - m0) / (m1 - m0)
      return [0, 1, 2].map(k => Math.round(c0[k] + (c1[k] - c0[k]) * t)).concat(a0 + (a1 - a0) * t)
    }
  }
  const last = RAIN_SCALE[RAIN_SCALE.length - 1]
  return [...last[1], last[2]]
}

/** Repaint precipitation pixels in place (RGBA bytes, as from getImageData). */
export function recolorPrecip(data) {
  for (let i = 0; i < data.length; i += 4) {
    const a = data[i + 3]
    if (a === 0) continue
    const mm = precipMm(data[i], data[i + 1], data[i + 2], a)
    if (mm < 0.1) { data[i + 3] = 0; continue }
    const [r, g, b, alpha] = rainColour(mm)
    data[i] = r; data[i + 1] = g; data[i + 2] = b
    data[i + 3] = Math.round(alpha * 255)
  }
  return data
}

/** Repaint cloud pixels in place (RGBA bytes, as from getImageData). */
export function recolorClouds(data) {
  for (let i = 0; i < data.length; i += 4) {
    const a = data[i + 3]
    if (a === 0) continue
    const pct = cloudPct(data[i], data[i + 1], data[i + 2], a)
    data[i] = CLOUD_RGB[0]; data[i + 1] = CLOUD_RGB[1]; data[i + 2] = CLOUD_RGB[2]
    data[i + 3] = Math.round(cloudAlpha(pct) * 255)
  }
  return data
}

// ── Temperature ──────────────────────────────────────────────────────────────
// OWM's temp_new palette: [°C, r, g, b]. It saturates at both ends (≤ −40 and ≥ 30 decode as such).
const OWM_TEMP = [
  [-40, 130, 22, 146], [-30, 130, 87, 219], [-20, 32, 140, 236], [-10, 32, 196, 232],
  [0, 35, 221, 221], [10, 194, 255, 40], [20, 255, 240, 40], [25, 255, 194, 40], [30, 252, 128, 20],
]

/** °C for an OWM temp_new pixel: the nearest point on the palette's colour path; null if transparent. */
export function tempC(r, g, b, a) {
  if (a === 0) return null
  let best = OWM_TEMP[0][0], bestD = Infinity
  for (let i = 1; i < OWM_TEMP.length; i++) {
    const [t0, r0, g0, b0] = OWM_TEMP[i - 1]
    const [t1, r1, g1, b1] = OWM_TEMP[i]
    const dr = r1 - r0, dg = g1 - g0, db = b1 - b0
    const len2 = dr * dr + dg * dg + db * db
    const u = len2 ? Math.max(0, Math.min(1, ((r - r0) * dr + (g - g0) * dg + (b - b0) * db) / len2)) : 0
    const er = r0 + dr * u - r, eg = g0 + dg * u - g, eb = b0 + db * u - b
    const d = er * er + eg * eg + eb * eb
    if (d < bestD) { bestD = d; best = t0 + (t1 - t0) * u }
  }
  return best
}

// Output: 2 °C bands on a cool-to-warm scale that stops at amber and brown. Saturated red and orange
// mean fire and SOS on this map, so heat is never painted in them. A darker contour where the band
// changes shows the gradient even when a whole region is within a few degrees.
export const TEMP_BAND_C = 2
export const TEMP_SCALE = [
  [-20, [59, 15, 112]], [-10, [62, 74, 158]], [0, [44, 127, 184]], [5, [65, 182, 196]],
  [10, [127, 205, 187]], [15, [199, 233, 180]], [20, [253, 230, 138]], [25, [251, 191, 36]],
  [30, [180, 83, 9]],
]
const TEMP_FILL_ALPHA    = 0.42
const TEMP_CONTOUR_ALPHA = 0.7
const TEMP_CONTOUR_RGB   = [20, 24, 32]

function tempColour(c) {
  if (c <= TEMP_SCALE[0][0]) return TEMP_SCALE[0][1]
  for (let i = 1; i < TEMP_SCALE.length; i++) {
    const [t1, c1] = TEMP_SCALE[i]
    if (c <= t1) {
      const [t0, c0] = TEMP_SCALE[i - 1]
      const t = (c - t0) / (t1 - t0)
      return [0, 1, 2].map(k => Math.round(c0[k] + (c1[k] - c0[k]) * t))
    }
  }
  return TEMP_SCALE[TEMP_SCALE.length - 1][1]
}

/**
 * Repaint temperature pixels in place: banded colour plus contours between bands. `width` is the
 * tile width in pixels (needed to compare a pixel with the one below it).
 */
export function recolorTemp(data, width = 256) {
  const n = data.length / 4
  const band = new Float64Array(n)
  const cache = new Map()   // the same colour recurs thousands of times per tile
  for (let p = 0; p < n; p++) {
    const i = p * 4
    if (data[i + 3] === 0) { band[p] = NaN; continue }
    const key = (data[i] << 16) | (data[i + 1] << 8) | data[i + 2]
    let c = cache.get(key)
    if (c === undefined) { c = tempC(data[i], data[i + 1], data[i + 2], data[i + 3]); cache.set(key, c) }
    band[p] = Math.floor(c / TEMP_BAND_C)
  }
  for (let p = 0; p < n; p++) {
    const i = p * 4
    if (Number.isNaN(band[p])) continue
    const right = (p + 1) % width !== 0 ? band[p + 1] : band[p]
    const below = p + width < n ? band[p + width] : band[p]
    const edge = (!Number.isNaN(right) && right !== band[p]) || (!Number.isNaN(below) && below !== band[p])
    if (edge) {
      data[i] = TEMP_CONTOUR_RGB[0]; data[i + 1] = TEMP_CONTOUR_RGB[1]; data[i + 2] = TEMP_CONTOUR_RGB[2]
      data[i + 3] = Math.round(TEMP_CONTOUR_ALPHA * 255)
    } else {
      const [r, g, b] = tempColour((band[p] + 0.5) * TEMP_BAND_C)
      data[i] = r; data[i + 1] = g; data[i + 2] = b
      data[i + 3] = Math.round(TEMP_FILL_ALPHA * 255)
    }
  }
  return data
}

/** CSS gradient for the legend, from the same scale (−20 … 30 °C). */
export function tempLegendGradient() {
  const lo = TEMP_SCALE[0][0], hi = TEMP_SCALE[TEMP_SCALE.length - 1][0]
  const stops = TEMP_SCALE.map(([t, [r, g, b]]) =>
    `rgba(${r},${g},${b},${TEMP_FILL_ALPHA + 0.3}) ${Math.round(100 * (t - lo) / (hi - lo))}%`)
  return `linear-gradient(to right, ${stops.join(', ')})`
}

/** The recolouring for a weather layer id, or null to show OWM's tiles unchanged. */
export function recolorFor(layerId) {
  return layerId === 'precipitation_new' ? recolorPrecip
    : layerId === 'clouds_new' ? recolorClouds
    : layerId === 'temp_new' ? recolorTemp
    : null
}
