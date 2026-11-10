// The fire map entry: burnt areas, suppression zones and hotspots (styles, sources, hit test, click and
// cursor handlers, the 60 s repaint). It is a map contribution in the shape of createMapShell's
// `install` (layers by declared id, then `setup`); the facade (useMap.js) installs it and delegates its
// five functions to the returned api. `onFireFeatureClick` and the tracker click stay in the facade:
// this entry reaches them through `ctx`.
// until step 2 (moves to src/modules/fire/map/)
import VectorLayer from 'ol/layer/Vector'
import VectorSource from 'ol/source/Vector'
import Feature from 'ol/Feature'
import GeoJSON from 'ol/format/GeoJSON'
import { circular as circularPolygon } from 'ol/geom/Polygon'
import { Circle, Fill, Stroke, Style, Text } from 'ol/style'
import RegularShape from 'ol/style/RegularShape'
import { hotspotStyleKey } from '../../lib/fireStyle'
import { hexToRgba } from '../../lib/color'

const FIRE_REPAINT_MS = 60_000
const HOTSPOT_HIT_TOLERANCE_PX = 6

// Fire colours live as tokens in style.css (--fire-*). OpenLayers paints on a canvas and
// cannot read CSS variables, so resolve them when a style is built. Fallbacks only matter
// without a DOM.
function fireToken(name, fallback) {
  try {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
    return v || fallback
  } catch { return fallback }
}

// Hotspot look per style key. Age fades fill and ring so the newest detections read first;
// state (dismissed / suppressed / extinguished) goes hollow and grey; a field report is a
// diamond, never a circle, so it cannot pass for a satellite detection.
function makeHotspotStyle(key, fieldReportLabel) {
  const ember    = fireToken('--fire-hotspot', '#ad1e57')
  const inactive = fireToken('--fire-inactive', '#8892aa')
  const ring     = fireToken('--text', '#e2e8f0')
  const circle = (radius, fill, stroke) => new Style({
    image: new Circle({ radius, fill: fill ? new Fill({ color: fill }) : undefined, stroke }),
  })
  // The ember is dark on a dark map (about 2.8:1 on --bg), so every hotspot carries a thin
  // light ring: newest is solid, older ones fade, but the ring never drops below what keeps
  // the dot findable on dark and satellite basemaps. No glow: glow is an alarm signal.
  const E = (alpha) => hexToRgba(ember, alpha, '#ad1e57')
  const R = (alpha) => hexToRgba(ring, alpha, '#e2e8f0')
  switch (key) {
    case 'age_24h': return circle(6, E(1),   new Stroke({ color: R(1),    width: 1.75 }))
    case 'age_3d':  return circle(5, E(0.7), new Stroke({ color: R(0.8),  width: 1.5 }))
    case 'age_7d':  return circle(4, E(0.45), new Stroke({ color: R(0.6), width: 1.25 }))
    case 'field_report':
      return new Style({
        image: new RegularShape({
          points: 4, radius: 9, angle: 0,
          fill: new Fill({ color: ember }), stroke: new Stroke({ color: ring, width: 2 }),
        }),
        text: fieldReportLabel ? new Text({
          text: fieldReportLabel, offsetY: 20,
          font: 'bold 12px system-ui',
          fill: new Fill({ color: ring }), stroke: new Stroke({ color: '#000', width: 3 }),
        }) : undefined,
      })
    case 'suppressed':
      return circle(5, null, new Stroke({ color: hexToRgba(inactive, 0.9, '#8892aa'), width: 1.5, lineDash: [3, 3] }))
    default: // dismissed, extinguished
      return circle(4, null, new Stroke({ color: hexToRgba(inactive, 0.8, '#8892aa'), width: 1.5 }))
  }
}

// Diagonal hatch: the cartographic sign for a burn scar, and unlike a flat wash it cannot be
// mistaken for a basemap fill. Sized in device pixels (the map canvas is), so the spacing looks
// the same on HiDPI screens. Null without a 2D canvas (jsdom): the caller falls back to a wash.
function makeHatchPattern(color) {
  try {
    const ratio = Math.max(1, Math.round(globalThis.devicePixelRatio || 1))
    const size = 9 * ratio
    const canvas = document.createElement('canvas')
    canvas.width = canvas.height = size
    const ctx = canvas.getContext('2d')
    if (!ctx) return null
    ctx.strokeStyle = color
    ctx.lineWidth = 1.5 * ratio
    ctx.lineCap = 'square'
    ctx.beginPath()
    // the main diagonal plus the two corner stubs, so the tiles join into unbroken lines
    ctx.moveTo(0, size); ctx.lineTo(size, 0)
    ctx.moveTo(-size / 2, size / 2); ctx.lineTo(size / 2, -size / 2)
    ctx.moveTo(size / 2, size * 1.5); ctx.lineTo(size * 1.5, size / 2)
    ctx.stroke()
    return ctx.createPattern(canvas, 'repeat')
  } catch { return null }
}

// Burnt areas are history, not alarm: charcoal, never red. Three passes so the area reads on
// light, dark and satellite basemaps alike: a light halo under the edge, a faint light wash plus
// a charcoal hatch inside, and a solid charcoal edge on top.
function makeBurntStyle() {
  const char = fireToken('--fire-burnt', '#4a2f1f')
  const halo = fireToken('--fire-burnt-halo', '#fff7ed')
  const hatch = makeHatchPattern(hexToRgba(char, 0.75, '#4a2f1f'))
  return [
    new Style({
      fill:   new Fill({ color: hexToRgba(halo, 0.22, '#fff7ed') }),
      stroke: new Stroke({ color: hexToRgba(halo, 0.85, '#fff7ed'), width: 5 }),
    }),
    new Style({
      fill:   new Fill({ color: hatch ?? hexToRgba(char, 0.3, '#4a2f1f') }),
      stroke: new Stroke({ color: char, width: 2 }),
    }),
  ]
}

// Suppression zones: an operator's "ignore detections here" circle. Muted, dashed and hollow like a
// suppressed hotspot (inactive grey-blue), never red, no glow. The label is canvas text, so a
// user-typed label can never act as markup; it is clipped so a long one cannot cover the map.
const ZONE_LABEL_MAX = 28
function makeZoneStyle(label) {
  const inactive = fireToken('--fire-inactive', '#8892aa')
  const ring     = fireToken('--text', '#e2e8f0')
  const text = String(label ?? '')
  return new Style({
    fill:   new Fill({ color: hexToRgba(inactive, 0.1, '#8892aa') }),
    stroke: new Stroke({ color: hexToRgba(inactive, 0.95, '#8892aa'), width: 1.5, lineDash: [6, 5] }),
    text: text ? new Text({
      text: text.length > ZONE_LABEL_MAX ? `${text.slice(0, ZONE_LABEL_MAX - 1)}…` : text,
      font: '600 12px system-ui',
      fill: new Fill({ color: ring }), stroke: new Stroke({ color: '#000', width: 3 }),
    }) : undefined,
  })
}

// The hotspot style cache and the field-report label belong to one hotspot layer; the layer factory
// creates them and `setup` finds them again through the layer.
const hotspotState = new WeakMap()   // layer -> { styles, label }

function makeBurntLayer() {
  let styleCache = null
  const layer = new VectorLayer({ source: new VectorSource(), visible: false })
  layer.setStyle(() => (styleCache ??= makeBurntStyle()))
  return layer
}

function makeZoneLayer() {
  // Suppression zones sit under the hotspots so a detection inside a zone stays clickable.
  return new VectorLayer({ source: new VectorSource(), visible: false })
}

function makeHotspotLayer() {
  const state = { styles: {}, label: '' }
  const layer = new VectorLayer({
    source: new VectorSource(), visible: false,
    style: (feature) => {
      const key = hotspotStyleKey(feature.getProperties(), Date.now())
      return (state.styles[key] ??= makeHotspotStyle(key, state.label))
    },
  })
  hotspotState.set(layer, state)
  return layer
}

function setupFireMap(shell, ctx) {
  const burntLayer   = shell.layer('fire-burnt')
  const zoneLayer    = shell.layer('fire-zones')
  const hotspotLayer = shell.layer('fire-hotspots')
  if (!burntLayer || !zoneLayer || !hotspotLayer) throw new Error('fire layers are not registered')
  const burntSource   = burntLayer.getSource()
  const zoneSource    = zoneLayer.getSource()
  const hotspotSource = hotspotLayer.getSource()
  const state   = hotspotState.get(hotspotLayer)
  const geojson = new GeoJSON()
  let timer = null

  // Read before clearing: a payload OpenLayers cannot parse keeps the previous features on
  // screen. Returns false so the caller can show the feed as failed (BP-03). The log line
  // carries no feature content.
  function replaceFeatures(source, fc, what) {
    let features
    try {
      features = geojson.readFeatures(fc, { featureProjection: 'EPSG:3857' })
    } catch {
      console.warn('fire layer: unreadable %s GeoJSON, keeping previous features', what)
      return false
    }
    source.clear(true)
    source.addFeatures(features)
    return true
  }

  const setBurntAreas = (fc) => replaceFeatures(burntSource, fc, 'burnt-area')
  const setHotspots   = (fc) => replaceFeatures(hotspotSource, fc, 'hotspot')

  // Zones arrive as plain rows ({ id, label, latitude, longitude, radius_m }). Each becomes a true
  // geodesic circle (a Web Mercator circle would be about a third too large at 42 N). A row that
  // cannot be drawn is skipped, so one bad zone never hides the rest.
  function setZones(list) {
    const features = []
    for (const z of Array.isArray(list) ? list : []) {
      const lon = Number(z?.longitude), lat = Number(z?.latitude), r = Number(z?.radius_m)
      if (!Number.isFinite(lon) || !Number.isFinite(lat) || !Number.isFinite(r) || r <= 0) continue
      const geometry = circularPolygon([lon, lat], r, 64).transform('EPSG:4326', 'EPSG:3857')
      const f = new Feature({ geometry, zoneId: z.id })
      f.setId(z.id)
      f.setStyle(makeZoneStyle(z.label))
      features.push(f)
    }
    zoneSource.clear(true)
    zoneSource.addFeatures(features)
    return features.length
  }

  function setFireLayerVisible(name, visible) {
    if (name === 'burnt')    burntLayer.setVisible(visible)
    if (name === 'hotspots') hotspotLayer.setVisible(visible)
    if (name === 'zones')    zoneLayer.setVisible(visible)
  }

  function setFireLabels({ fieldReport }) {
    state.label = fieldReport || ''
    for (const k of Object.keys(state.styles)) delete state.styles[k]
    hotspotLayer.changed()
  }

  const fireHit = (pixel) => {
    const map = shell.map
    const hotspot = map.forEachFeatureAtPixel(pixel, f => f, { layerFilter: l => l === hotspotLayer, hitTolerance: HOTSPOT_HIT_TOLERANCE_PX })
    if (hotspot) return { kind: 'hotspot', feature: hotspot }
    const burnt = map.forEachFeatureAtPixel(pixel, f => f, { layerFilter: l => l === burntLayer })
    return burnt ? { kind: 'burnt_area', feature: burnt } : null
  }

  // Fire features: a tracker wins when both are hit (the facade's tracker handler runs first and
  // stops the click); clicking bare map closes the popup. Without a mode only, so a placement or
  // measure click never reaches it.
  const offClick = shell.onClick((evt) => {
    if (!ctx.fireClickRegistered()) return false
    const hit = fireHit(evt.pixel)
    if (!hit) { ctx.reportFireClick(null); ctx.reportTrackerClick(null); return true }
    const props = { ...hit.feature.getProperties() }
    delete props.geometry
    ctx.reportFireClick({
      kind: hit.kind,
      properties: props,
      coordinate: hit.kind === 'hotspot' ? hit.feature.getGeometry().getCoordinates() : evt.coordinate,
    })
    return true
  }, { order: 20, id: 'fire-click' })

  const offMove = shell.onPointerMove((evt) => {
    if (ctx.trackerHit(evt.pixel)) return
    if (fireHit(evt.pixel)) shell.map.getTargetElement().style.cursor = 'pointer'
  }, { id: 'fire-cursor' })

  // Hotspots fade with age; repaint each minute so they do so without a refetch.
  shell.onMounted(() => {
    clearInterval(timer)
    timer = setInterval(() => { if (hotspotLayer.getVisible()) hotspotLayer.changed() }, FIRE_REPAINT_MS)
  })

  return {
    api: { setBurntAreas, setHotspots, setZones, setFireLayerVisible, setFireLabels },
    dispose() {
      clearInterval(timer)
      timer = null
      offClick()
      offMove()
    },
  }
}

export const LEGACY_FIRE_MAP = {   // until step 2
  name: 'fire',
  layers: {
    'fire-burnt': makeBurntLayer,
    'fire-zones': makeZoneLayer,
    'fire-hotspots': makeHotspotLayer,
  },
  setup: setupFireMap,
}
