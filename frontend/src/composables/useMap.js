import { onMounted, onUnmounted, ref, watch } from 'vue'
import Overlay from 'ol/Overlay'
import Map from 'ol/Map'
import View from 'ol/View'
import TileLayer from 'ol/layer/Tile'
import OSM from 'ol/source/OSM'
import XYZ from 'ol/source/XYZ'
import VectorLayer from 'ol/layer/Vector'
import VectorSource from 'ol/source/Vector'
import Feature from 'ol/Feature'
import Point from 'ol/geom/Point'
import LineString from 'ol/geom/LineString'
import { circular as circularPolygon } from 'ol/geom/Polygon'
import { fromLonLat, toLonLat } from 'ol/proj'
import GeoJSON from 'ol/format/GeoJSON'
import { Circle, Fill, Stroke, Style, Text } from 'ol/style'
import RegularShape from 'ol/style/RegularShape'
import Icon from 'ol/style/Icon'
import Graticule from 'ol/layer/Graticule'
import ScaleLine from 'ol/control/ScaleLine'
import { forward as toMGRS } from 'mgrs'
import { useSettings } from './useSettings'
import { normaliseGroups } from '../lib/groups'
import { freshnessOf, LIVE, LOST } from '../lib/freshness'
import { renderTrackerTooltip } from '../lib/trackerTooltip'
import { createLongPress } from '../lib/longPress'
import { hotspotStyleKey } from '../lib/fireStyle'
import { hexToRgba } from '../lib/color'
import { PHOTO_SIZE, markerZIndex, onPhotoLoaded, photoCanvas, photoImage, ringFor, safePhotoUrl } from '../lib/photoMarker'

const DEFAULT_COLOR = '#3b82f6'

// Long press on touch: 600 ms held within 10 px.
const LONG_PRESS_MS = 600
const LONG_PRESS_SLOP_PX = 10
const LONG_PRESS_DEDUPE_MS = 800

function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371
  const φ1 = lat1 * Math.PI / 180, φ2 = lat2 * Math.PI / 180
  const Δφ = (lat2 - lat1) * Math.PI / 180, Δλ = (lon2 - lon1) * Math.PI / 180
  const a = Math.sin(Δφ/2)**2 + Math.cos(φ1) * Math.cos(φ2) * Math.sin(Δλ/2)**2
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

function bearingDeg(lat1, lon1, lat2, lon2) {
  const φ1 = lat1 * Math.PI / 180, φ2 = lat2 * Math.PI / 180
  const Δλ = (lon2 - lon1) * Math.PI / 180
  const y = Math.sin(Δλ) * Math.cos(φ2)
  const x = Math.cos(φ1) * Math.sin(φ2) - Math.sin(φ1) * Math.cos(φ2) * Math.cos(Δλ)
  return ((Math.atan2(y, x) * 180 / Math.PI) + 360) % 360
}

export const BASEMAPS = [
  { id: 'osm',          label: 'Street' },
  { id: 'dark',         label: 'Dark' },
  { id: 'satellite',    label: 'Satellite' },
  { id: 'topo',         label: 'Topo' },
  { id: 'bgmountains',  label: 'BG Mountains', local: true },
]

const TILE_SERVER = 'http://localhost:8080'

const { bgMountainsOffline } = useSettings()

function makeBgMountainsSource() {
  if (bgMountainsOffline.value) {
    return new XYZ({ url: '/tiles/bgmountains/{z}/{x}/{y}.png', attributions: '© BGMountains', maxZoom: 18 })
  }
  return new XYZ({ url: 'https://bgmtile.kade.si/{z}/{x}/{y}.png', attributions: '© BGMountains', crossOrigin: 'anonymous', maxZoom: 18 })
}

function makeBasemapLayer(id) {
  const sources = {
    osm: new OSM(),
    dark: new XYZ({
      url: 'https://{a-d}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
      attributions: '© CartoDB',
    }),
    satellite: new XYZ({
      url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      attributions: '© Esri',
    }),
    topo: new XYZ({
      url: 'https://{a-c}.tile.opentopomap.org/{z}/{x}/{y}.png',
      attributions: '© OpenTopoMap',
    }),
    bgmountains: makeBgMountainsSource(),
  }
  return new TileLayer({ source: sources[id] ?? sources.osm })
}

function gridInterval(zoom) {
  if (zoom >= 14) return 0.01
  if (zoom >= 11) return 0.1
  if (zoom >= 8)  return 1
  return 5
}

function makeMGRSLabel(lon, lat) {
  try {
    const mgrs = toMGRS([lon, lat], 0)
    return mgrs.slice(0, 7)
  } catch {
    return ''
  }
}

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

export function makeMarkerStyle(color, isSOS, name, isTeam, freshness, noFix) {
  const radius   = isSOS ? 10 : isTeam ? 10 : 7
  const isStale  = freshness !== LIVE
  const isLost   = freshness === LOST
  // Lost contact fades further than merely stale, so "we haven't heard from them in half an
  // hour" is distinguishable from "they're a few minutes overdue" at a glance.
  const fillColor = isSOS ? '#ef4444'
    : isLost  ? 'rgba(156,163,175,0.22)'
    : isStale ? 'rgba(156,163,175,0.45)'
    : color
  const strokeCol = isStale ? 'rgba(255,255,255,0.35)' : '#fff'

  const style = new Style({
    zIndex: markerZIndex(isSOS, freshness),
    image: new Circle({
      radius,
      fill:   new Fill({ color: fillColor }),
      // Dashed ring = in radio contact but no satellite fix: the position shown is the last
      // known one, not where they are now.
      stroke: new Stroke({
        color:    noFix ? '#facc15' : strokeCol,
        width:    isTeam ? 3 : 2,
        lineDash: noFix ? [3, 2] : undefined,
      }),
    }),
    text: new Text({
      text:    name || '',
      offsetY: -(radius + 10),
      fill:    new Fill({ color: '#fff' }),
      stroke:  new Stroke({ color: '#000', width: 3 }),
      font:    isTeam ? 'bold 14px system-ui' : 'bold 13px system-ui',
    }),
  })
  return style
}

// Photo variant of the marker: same label, same states, the dot replaced by a round photo with
// a state ring. Returns null (the caller keeps the dot) while the image is loading, after it
// failed, or when the browser cannot draw it.
export function makePhotoMarkerStyle(url, color, isSOS, name, freshness, noFix) {
  const img = photoImage(url)
  if (!img) return null
  const dpr = Math.min(2, globalThis.devicePixelRatio || 1)
  const canvas = photoCanvas(url, img, ringFor({ color, isSOS, freshness, noFix }), dpr)
  if (!canvas) return null
  return new Style({
    image: new Icon({ img: canvas, imgSize: [canvas.width, canvas.height], scale: 1 / dpr }),
    zIndex: markerZIndex(isSOS, freshness),
    text: new Text({
      text:    name || '',
      offsetY: -(PHOTO_SIZE / 2 + 10),
      fill:    new Fill({ color: '#fff' }),
      stroke:  new Stroke({ color: '#000', width: 3 }),
      font:    'bold 13px system-ui',
    }),
  })
}

function makeTrailStyle(color) {
  return new Style({
    stroke: new Stroke({
      color:    hexToRgba(color, 0.65),
      width:    2.5,
      lineDash: [6, 3],
    }),
  })
}

function formatCheckpointTime(recordedAt) {
  if (!recordedAt) return ''
  const d = new Date(recordedAt)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function makeCheckpointStyle(color, index, isLast, showLabels, recordedAt) {
  const label = showLabels
    ? (formatCheckpointTime(recordedAt) || String(index + 1))
    : ''
  return new Style({
    image: new Circle({
      radius: isLast ? 6 : 4,
      fill:   new Fill({ color: isLast ? color : hexToRgba(color, 0.6) }),
      stroke: new Stroke({ color: '#fff', width: isLast ? 2 : 1 }),
    }),
    text: showLabels ? new Text({
      text:         label,
      font:         `bold ${isLast ? 10 : 9}px system-ui`,
      fill:         new Fill({ color: '#fff' }),
      stroke:       new Stroke({ color: '#000', width: 2 }),
      offsetY:      isLast ? -14 : -12,
      textBaseline: 'bottom',
    }) : undefined,
  })
}

export function useMap(mapRef, positionList, trails, onCursorMGRS, onMeasure, groupsMap, onHQPlaced, showPhotos = ref(true)) {
  let map = null
  let basemapLayer = makeBasemapLayer('osm')
  let checkpointNumbersVisible = false
  let mgrsLabelMode = false
  let latLonGridVisible = false
  let measureMode   = false
  let measurePoints = []
  let staleTimer    = null
  let hqPlacementMode = false
  let hqLabel = 'ЩАБ'

  // Marker layer
  const source      = new VectorSource()
  const vectorLayer = new VectorLayer({ source, zIndex: 10 })

  // Trail line layer
  const trailSource = new VectorSource()
  const trailLayer  = new VectorLayer({ source: trailSource, zIndex: 5, visible: false })

  // Checkpoint dot layer
  const checkpointSource = new VectorSource()
  const checkpointLayer  = new VectorLayer({ source: checkpointSource, zIndex: 6, visible: false })

  // Fire layers: history (burnt areas) and detections (hotspots) sit under the trackers and
  // trails, hidden until the operator turns them on.
  const geojson       = new GeoJSON()
  const burntSource   = new VectorSource()
  const burntLayer    = new VectorLayer({ source: burntSource, zIndex: 3, visible: false })
  const hotspotSource = new VectorSource()
  const hotspotStyles = {}
  let   fieldReportLabel = ''
  const hotspotLayer  = new VectorLayer({
    source: hotspotSource, zIndex: 3.5, visible: false,
    style: (feature) => {
      const key = hotspotStyleKey(feature.getProperties(), Date.now())
      return (hotspotStyles[key] ??= makeHotspotStyle(key, fieldReportLabel))
    },
  })
  let burntStyleCache = null
  burntLayer.setStyle(() => (burntStyleCache ??= makeBurntStyle()))
  // Suppression zones sit under the hotspots so a detection inside a zone stays clickable.
  const zoneSource = new VectorSource()
  const zoneLayer  = new VectorLayer({ source: zoneSource, zIndex: 3.4, visible: false })
  let fireTimer = null
  let fireClickCb = null
  let trackerClickCb = null
  let contextMenuCb = null
  let onContextMenuEvent = null, onPressDown = null, onPressMove = null, endPressFn = null, longPress = null

  // Measure layer
  const measureSource = new VectorSource()
  const measureLayer  = new VectorLayer({ source: measureSource, zIndex: 20 })

  // HQ layer
  const hqSource = new VectorSource()
  const hqLayer  = new VectorLayer({ source: hqSource, zIndex: 15 })

  // Weather overlay layer — created/destroyed on demand
  let activeWeatherLayer = null

  // MGRS latitude band letters C–X (8° bands starting at −80°)
  const MGRS_BANDS = 'CDEFGHJKLMNPQRSTUVWX'
  function mgrsLatBand(lat) {
    const idx = Math.floor((lat + 80) / 8)
    return MGRS_BANDS[Math.max(0, Math.min(idx, MGRS_BANDS.length - 1))] ?? ''
  }

  const graticule = new Graticule({
    strokeStyle: new Stroke({ color: 'rgba(0,0,0,0.85)', width: 2 }),
    showLabels: true,
    lonLabelStyle: new Text({
      font: 'bold 13px monospace',
      fill: new Fill({ color: '#000' }),
      stroke: new Stroke({ color: '#fff', width: 4 }),
      textBaseline: 'bottom',
      textAlign: 'center',
      offsetY: -4,
    }),
    latLabelStyle: new Text({
      font: 'bold 13px monospace',
      fill: new Fill({ color: '#000' }),
      stroke: new Stroke({ color: '#fff', width: 4 }),
      textAlign: 'right',
      textBaseline: 'bottom',
      offsetX: -6,
      offsetY: -4,
    }),
    lonLabelFormatter: (lon) => {
      if (mgrsLabelMode) {
        try {
          const center = map?.getView().getCenter()
          if (center) {
            const [, lat] = toLonLat(center)
            const zoom = map.getView().getZoom() ?? 7
            const acc = zoom >= 14 ? 2 : zoom >= 11 ? 1 : 0
            return toMGRS([lon, lat], acc)
          }
        } catch { /* ignore */ }
        return ''
      }
      const abs = parseFloat(Math.abs(lon).toFixed(5)).toString()
      return `${abs}°${lon >= 0 ? 'E' : 'W'}`
    },
    latLabelFormatter: (lat) => {
      if (mgrsLabelMode) {
        try {
          const center = map?.getView().getCenter()
          if (center) {
            const [lon] = toLonLat(center)
            const zoom = map.getView().getZoom() ?? 7
            const acc = zoom >= 14 ? 2 : zoom >= 11 ? 1 : 0
            return toMGRS([lon, lat], acc)
          }
        } catch { /* ignore */ }
        return mgrsLatBand(lat)
      }
      const abs = parseFloat(Math.abs(lat).toFixed(5)).toString()
      return `${abs}°${lat >= 0 ? 'N' : 'S'}`
    },
    visible: false,
    zIndex: 4,
  })

  let activeBasemapId = 'osm'

  // `recolor(data, width)` (lib/weatherTiles.js) repaints each tile's RGBA bytes in place; without it the
  // provider's tiles are shown as they come.
  function setWeatherLayer(url, recolor = null) {
    if (activeWeatherLayer) {
      map.removeLayer(activeWeatherLayer)
      activeWeatherLayer = null
    }
    if (!url || !map) return
    const source = new XYZ({ url, crossOrigin: 'anonymous' })
    if (recolor) source.setTileLoadFunction((tile, src) => loadRecolored(tile, src, recolor))
    activeWeatherLayer = new TileLayer({ source, opacity: 1.0, zIndex: 2 })
    map.addLayer(activeWeatherLayer)
  }

  // Load a tile, repaint it on a canvas and hand OpenLayers the result. Any failure (no 2D
  // canvas, a tainted image) falls back to the original tile rather than a hole in the layer.
  function loadRecolored(tile, src, recolor) {
    const target = tile.getImage()
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => {
      try {
        const canvas = document.createElement('canvas')
        canvas.width = img.naturalWidth
        canvas.height = img.naturalHeight
        const ctx = canvas.getContext('2d', { willReadFrequently: true })
        ctx.drawImage(img, 0, 0)
        const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height)
        recolor(pixels.data, canvas.width)
        ctx.putImageData(pixels, 0, 0)
        target.src = canvas.toDataURL()
      } catch {
        target.src = src
      }
    }
    img.onerror = () => { target.src = src }   // let OpenLayers see the failure itself
    img.src = src
  }

  function setBasemap(id) {
    if (!map) return
    activeBasemapId = id
    map.getLayers().removeAt(0)
    basemapLayer = makeBasemapLayer(id)
    map.getLayers().insertAt(0, basemapLayer)
  }

  watch(bgMountainsOffline, () => {
    if (activeBasemapId === 'bgmountains') setBasemap('bgmountains')
  })

  function forceGraticuleRedraw() {
    graticule.renderedExtent_ = null
    map?.render()
  }

  function setMGRSGrid(visible) {
    mgrsLabelMode = visible
    graticule.setVisible(visible || latLonGridVisible)
    forceGraticuleRedraw()
  }

  function setLatLonGrid(visible) {
    latLonGridVisible = visible
    graticule.setVisible(visible || mgrsLabelMode)
    forceGraticuleRedraw()
  }

  // One malformed row must never blank every marker (B50): isolate each upsert.
  function safeUpsert(pos) {
    try { upsertFeature(pos) } catch { console.warn('Skipped a position that could not be drawn') }
  }

  // One place decides how a marker looks. Photo only for an individual (never the team dot in
  // the groups view) with the setting on and a same-origin photo that has loaded; every other
  // case, including a failed load, is the dot.
  function styleFor(pos) {
    const leaderGroup = pos.groups?.find(g => g.is_leader)
    const color     = leaderGroup?.color ?? pos.groups?.[0]?.color ?? DEFAULT_COLOR
    const freshness = freshnessOf(pos)
    const noFix     = pos.gnss_valid === false
    const isTeam    = !!pos.displayLabel
    const label     = pos.displayLabel || pos.full_name || pos.device_name || String(pos.dev_sn ?? '')
    if (!isTeam && showPhotos.value !== false) {
      const url = safePhotoUrl(pos.photo_url)
      const photo = url && makePhotoMarkerStyle(url, color, pos.sos_active, label, freshness, noFix)
      if (photo) return photo
    }
    return makeMarkerStyle(color, pos.sos_active, label, isTeam, freshness, noFix)
  }

  // Photos finish loading in separate tasks, so a microtask would not merge them (N restyles of N
  // markers on start). One restyle per animation frame (50 ms timer where there is no rAF) covers
  // every photo that arrived meanwhile (B56).
  let restyleHandle = null
  let restyleViaRaf = false
  function scheduleRestyle() {
    if (restyleHandle != null) return
    const run = () => { restyleHandle = null; restyleAll() }
    restyleViaRaf = typeof requestAnimationFrame === 'function'
    restyleHandle = restyleViaRaf ? requestAnimationFrame(run) : setTimeout(run, 50)
  }
  // Every open map hears about every finished photo, not only the one that started the load.
  const offPhotoLoaded = onPhotoLoaded(scheduleRestyle)
  function restyleAll() {
    source.getFeatures().forEach(f => {
      const pos = f.get('pos')
      if (pos) f.setStyle(styleFor(pos))
    })
  }

  function upsertFeature(rawPos) {
    const pos = normaliseGroups(rawPos)
    const id  = pos.device_id

    let feature = source.getFeatureById(id)
    if (!feature) {
      feature = new Feature({ geometry: new Point([0, 0]) })
      feature.setId(id)
      source.addFeature(feature)
    }
    feature.getGeometry().setCoordinates(fromLonLat([pos.longitude, pos.latitude]))
    feature.setStyle(styleFor(pos))
    feature.setProperties({ pos }, true)
  }

  function removeStaleFeatures(currentIds) {
    const set = new Set(currentIds)
    source.getFeatures().forEach(f => {
      if (!set.has(f.getId())) source.removeFeature(f)
    })
  }

  function upsertTrail(deviceId, points) {
    const fid = `trail-${deviceId}`
    if (!points || points.length < 2) {
      const f = trailSource.getFeatureById(fid)
      if (f) trailSource.removeFeature(f)
      return
    }

    const coords = points.map(p => fromLonLat([p.lon, p.lat]))
    // Look up the device color from its marker
    const markerFeature = source.getFeatureById(deviceId)
    const color = markerFeature?.get('pos')?.groups?.[0]?.color ?? DEFAULT_COLOR

    let feature = trailSource.getFeatureById(fid)
    if (!feature) {
      feature = new Feature({ geometry: new LineString(coords) })
      feature.setId(fid)
      trailSource.addFeature(feature)
    } else {
      feature.getGeometry().setCoordinates(coords)
    }
    feature.setStyle(makeTrailStyle(color))
  }

  function removeStaleTrails(currentIds) {
    const set = new Set(currentIds.map(id => `trail-${id}`))
    trailSource.getFeatures().forEach(f => {
      if (!set.has(f.getId())) trailSource.removeFeature(f)
    })
  }

  function upsertCheckpoints(deviceId, points) {
    // Remove old checkpoints for this device
    checkpointSource.getFeatures()
      .filter(f => f.get('deviceId') === deviceId)
      .forEach(f => checkpointSource.removeFeature(f))

    if (!points || points.length === 0) return

    const markerFeature = source.getFeatureById(deviceId)
    const color = markerFeature?.get('pos')?.groups?.[0]?.color ?? DEFAULT_COLOR

    points.forEach((p, i) => {
      const isLast = i === points.length - 1
      const f = new Feature({ geometry: new Point(fromLonLat([p.lon, p.lat])) })
      // Label with the server clock, same as every other time the operator sees — a device
      // with a skewed GNSS clock would otherwise stamp checkpoints with times that never were.
      f.setStyle(makeCheckpointStyle(color, i, isLast, checkpointNumbersVisible, p.received_at ?? p.recorded_at))
      f.set('deviceId', deviceId)
      f.set('recordedAt', p.recorded_at)
      f.set('cpIndex', i)
      f.set('cpIsLast', isLast)
      f.set('cpColor', color)
      checkpointSource.addFeature(f)
    })
  }

  function removeStaleCheckpoints(currentIds) {
    const set = new Set(currentIds)
    const toRemove = checkpointSource.getFeatures()
      .filter(f => !set.has(f.get('deviceId')))
    toRemove.forEach(f => checkpointSource.removeFeature(f))
  }

  function setTrailVisible(visible) {
    trailLayer.setVisible(visible)
    checkpointLayer.setVisible(visible)
  }

  function setCheckpointNumbers(visible) {
    checkpointNumbersVisible = visible
    checkpointSource.getFeatures().forEach(f => {
      f.setStyle(makeCheckpointStyle(
        f.get('cpColor'), f.get('cpIndex'), f.get('cpIsLast'), visible, f.get('recordedAt'),
      ))
    })
  }

  onMounted(() => {
    // Hover tooltip element — created programmatically so it lives inside OL's viewport
    const tooltipEl = document.createElement('div')
    Object.assign(tooltipEl.style, {
      position:        'absolute',
      background:      'rgba(15,15,20,0.88)',
      color:           '#fff',
      padding:         '6px 10px',
      borderRadius:    '6px',
      fontSize:        '12px',
      pointerEvents:   'none',
      whiteSpace:      'nowrap',
      boxShadow:       '0 2px 8px rgba(0,0,0,0.5)',
      border:          '1px solid rgba(255,255,255,0.1)',
      lineHeight:      '1.5',
      display:         'none',
    })

    const tooltip = new Overlay({
      element:     tooltipEl,
      offset:      [14, 0],
      positioning: 'center-left',
      stopEvent:   false,
    })

    map = new Map({
      target:   mapRef.value,
      layers:   [basemapLayer, burntLayer, zoneLayer, hotspotLayer, graticule, trailLayer, checkpointLayer, hqLayer, vectorLayer, measureLayer],
      view:     new View({ center: fromLonLat([25.0, 42.5]), zoom: 7 }),
      overlays: [tooltip],
      controls: [new ScaleLine({ units: 'metric', bar: false, minWidth: 100 })],
    })

    map.on('pointermove', (evt) => {
      if (evt.dragging) return
      const feature = map.forEachFeatureAtPixel(evt.pixel, f => f, {
        layerFilter: l => l === vectorLayer,
        hitTolerance: 5,
      })
      if (feature) {
        const stored = feature.get('pos')
        const pos    = positionList.value?.find(p => p.device_id === feature.getId()) ?? stored
        const leaderGroup = pos.displayLabel ? pos.groups?.find(g => g.is_leader) : null
        const gDetail     = leaderGroup ? (groupsMap?.value ?? {})[leaderGroup.id] : null
        renderTrackerTooltip(tooltipEl, pos, gDetail, { showPhotos: showPhotos.value !== false })
        tooltipEl.style.display = 'block'
        tooltip.setPosition(evt.coordinate)
        map.getTargetElement().style.cursor = 'pointer'
      } else {
        tooltipEl.style.display = 'none'
        tooltip.setPosition(undefined)
        map.getTargetElement().style.cursor = ''
      }

      // cursor coordinate readout
      if (onCursorMGRS) {
        try {
          const [lon, lat] = toLonLat(evt.coordinate)
          onCursorMGRS({ mgrs: toMGRS([lon, lat], 5), lat, lon })
        } catch {
          onCursorMGRS(null)
        }
      }
    })

    // Measure click handler
    const ptStyle = (label) => new Style({
      image: new Circle({
        radius: 6,
        fill:   new Fill({ color: '#1d4ed8' }),
        stroke: new Stroke({ color: '#fff', width: 2 }),
      }),
      text: new Text({
        text: label, offsetY: -16,
        fill:   new Fill({ color: '#1d4ed8' }),
        stroke: new Stroke({ color: '#000', width: 3 }),
        font: 'bold 12px system-ui',
      }),
    })

    // The release of a long press raises a click: it belongs to the menu, not to the map.
    const clickSwallowed = () => !!longPress?.shouldSwallowClick()

    map.on('click', (evt) => {
      if (clickSwallowed()) return
      if (hqPlacementMode) {
        const [lon, lat] = toLonLat(evt.coordinate)
        onHQPlaced?.({ lat, lon })
        return
      }
      if (!measureMode) return
      const [lon, lat] = toLonLat(evt.coordinate)

      if (measurePoints.length >= 2) {
        measurePoints = []
        measureSource.clear()
        onMeasure?.(null)
      }

      measurePoints.push({ lat, lon, coord: evt.coordinate })

      const f = new Feature({ geometry: new Point(evt.coordinate) })
      f.setStyle(ptStyle(measurePoints.length === 1 ? 'A' : 'B'))
      measureSource.addFeature(f)

      if (measurePoints.length === 2) {
        const [a, b] = measurePoints
        const line = new Feature({ geometry: new LineString([a.coord, b.coord]) })
        line.setStyle(new Style({ stroke: new Stroke({ color: '#1d4ed8', width: 2, lineDash: [6, 4] }) }))
        measureSource.addFeature(line)
        onMeasure?.({ distKm: haversineKm(a.lat, a.lon, b.lat, b.lon), bearing: bearingDeg(a.lat, a.lon, b.lat, b.lon) })
      }
    })

    // Fire features: a tracker wins when both are hit; clicking bare map closes the popup.
    const fireHit = (pixel) => {
      const hotspot = map.forEachFeatureAtPixel(pixel, f => f, { layerFilter: l => l === hotspotLayer, hitTolerance: 6 })
      if (hotspot) return { kind: 'hotspot', feature: hotspot }
      const burnt = map.forEachFeatureAtPixel(pixel, f => f, { layerFilter: l => l === burntLayer })
      return burnt ? { kind: 'burnt_area', feature: burnt } : null
    }
    const trackerHit = (pixel) => map.hasFeatureAtPixel(pixel, { layerFilter: l => l === vectorLayer, hitTolerance: 5 })

    map.on('click', (evt) => {
      if (clickSwallowed()) return
      if (hqPlacementMode || measureMode || !fireClickCb) return
      // A tracker click opens the tracker popup and closes any fire popup.
      if (trackerHit(evt.pixel)) {
        fireClickCb(null)
        const marker = map.forEachFeatureAtPixel(evt.pixel, f => f, { layerFilter: l => l === vectorLayer, hitTolerance: 5 })
        if (marker && marker.getId() != null) trackerClickCb?.(String(marker.getId()))
        return
      }
      const hit = fireHit(evt.pixel)
      if (!hit) { fireClickCb(null); trackerClickCb?.(null); return }
      const props = { ...hit.feature.getProperties() }
      delete props.geometry
      fireClickCb({
        kind: hit.kind,
        properties: props,
        coordinate: hit.kind === 'hotspot' ? hit.feature.getGeometry().getCoordinates() : evt.coordinate,
      })
    })

    map.on('pointermove', (evt) => {
      if (evt.dragging || hqPlacementMode || measureMode) return
      if (trackerHit(evt.pixel)) return
      if (fireHit(evt.pixel)) map.getTargetElement().style.cursor = 'pointer'
    })

    // "Report fire here": right-click on a mouse, long-press on touch. Both hand over the clicked
    // coordinate (EPSG:3857) and its pixel inside the map element; the view decides what to offer.
    // Touch browsers may fire `contextmenu` after a long press as well, so one gesture is reported
    // once (a second report within LONG_PRESS_DEDUPE_MS is dropped).
    const viewport = map.getViewport()
    let lastContextAt = -Infinity
    const reportContext = (clientX, clientY) => {
      const now = performance.now()
      if (now - lastContextAt < LONG_PRESS_DEDUPE_MS) return
      lastContextAt = now
      if (!contextMenuCb || hqPlacementMode || measureMode) return
      const pixel = map.getEventPixel({ clientX, clientY })
      const coordinate = map.getCoordinateFromPixel(pixel)
      if (coordinate) contextMenuCb({ coordinate, pixel })
    }
    onContextMenuEvent = (e) => { e.preventDefault(); reportContext(e.clientX, e.clientY) }
    viewport.addEventListener('contextmenu', onContextMenuEvent)

    longPress = createLongPress({ onLongPress: reportContext, ms: LONG_PRESS_MS, slopPx: LONG_PRESS_SLOP_PX })
    onPressDown = longPress.down
    onPressMove = longPress.move
    viewport.addEventListener('pointerdown', onPressDown)
    viewport.addEventListener('pointermove', onPressMove)
    viewport.addEventListener('pointerup', longPress.end)
    viewport.addEventListener('pointercancel', longPress.end)
    endPressFn = longPress.end

    // Hotspots fade with age; repaint each minute so they do so without a refetch.
    fireTimer = setInterval(() => { if (hotspotLayer.getVisible()) hotspotLayer.changed() }, 60_000)

    // Re-evaluate stale state every minute without needing a new WS frame
    staleTimer = setInterval(() => {
      restyleAll()
    }, 60_000)

  })

  watch(positionList, (list) => {
    list.forEach(safeUpsert)
    removeStaleFeatures(list.map(p => p.device_id))
  }, { deep: true })

  // The setting changed: redraw every marker now.
  watch(showPhotos, () => {
    ;(positionList.value ?? []).forEach(safeUpsert)
    restyleAll()
  })

  watch(trails, (trailMap) => {
    Object.entries(trailMap).forEach(([deviceId, points]) => {
      upsertTrail(deviceId, points)
      upsertCheckpoints(deviceId, points)
    })
    removeStaleTrails(Object.keys(trailMap))
    removeStaleCheckpoints(Object.keys(trailMap))
  }, { deep: true })

  onUnmounted(() => {
    offPhotoLoaded()
    if (restyleHandle != null) {
      restyleViaRaf ? cancelAnimationFrame(restyleHandle) : clearTimeout(restyleHandle)
      restyleHandle = null
    }
    const viewport = map?.getViewport()
    if (viewport) {
      viewport.removeEventListener('contextmenu', onContextMenuEvent)
      viewport.removeEventListener('pointerdown', onPressDown)
      viewport.removeEventListener('pointermove', onPressMove)
      viewport.removeEventListener('pointerup', endPressFn)
      viewport.removeEventListener('pointercancel', endPressFn)
    }
    endPressFn?.()
    map?.setTarget(null)
    clearInterval(staleTimer)
    clearInterval(fireTimer)
  })

  function setMeasureMode(on) {
    measureMode = on
    if (!on) {
      measurePoints = []
      measureSource.clear()
      onMeasure?.(null)
    }
    if (map) map.getTargetElement().style.cursor = on ? 'crosshair' : ''
  }

  function makeHQStyle(label) {
    return new Style({
      image: new RegularShape({
        points:  4,
        radius:  15,
        radius2: 4,
        angle:   0,
        fill:    new Fill({ color: '#fbbf24' }),
        stroke:  new Stroke({ color: '#000', width: 2 }),
      }),
      text: new Text({
        text:    label || 'ЩАБ',
        offsetY: -22,
        font:    'bold 13px system-ui',
        fill:    new Fill({ color: '#fbbf24' }),
        stroke:  new Stroke({ color: '#000', width: 3 }),
      }),
    })
  }

  function setHQ(loc, label) {
    hqLabel = label || hqLabel
    hqSource.clear()
    if (!loc) return
    const f = new Feature({ geometry: new Point(fromLonLat([loc.lon, loc.lat])) })
    f.setId('hq')
    f.setStyle(makeHQStyle(hqLabel))
    hqSource.addFeature(f)
  }

  function setHQPlacementMode(on) {
    hqPlacementMode = on
    if (map) map.getTargetElement().style.cursor = on ? 'crosshair' : ''
  }

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

  function setBurntAreas(fc)  { return replaceFeatures(burntSource, fc, 'burnt-area') }
  function setHotspots(fc)    { return replaceFeatures(hotspotSource, fc, 'hotspot') }

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
    fieldReportLabel = fieldReport || ''
    for (const k of Object.keys(hotspotStyles)) delete hotspotStyles[k]
    hotspotLayer.changed()
  }

  function onFireFeatureClick(cb) { fireClickCb = cb }
  // A click on a tracker marker passes its device id; a click on bare map passes null.
  function onTrackerClick(cb) { trackerClickCb = cb }
  function onMapContextMenu(cb) { contextMenuCb = cb }

  function refreshMarkers(list) {
    list.forEach(safeUpsert)
    removeStaleFeatures(list.map(p => p.device_id))
  }

  return { map: () => map, setBasemap, setMGRSGrid, setLatLonGrid, setTrailVisible, setCheckpointNumbers, setMeasureMode, setWeatherLayer, refreshMarkers, setHQ, setHQPlacementMode, setBurntAreas, setHotspots, setFireLayerVisible, setFireLabels, onFireFeatureClick, setZones, onTrackerClick, onMapContextMenu }
}
