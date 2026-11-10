import { onMounted, onUnmounted, ref, watch } from 'vue'
import Overlay from 'ol/Overlay'
import View from 'ol/View'
import TileLayer from 'ol/layer/Tile'
import OSM from 'ol/source/OSM'
import XYZ from 'ol/source/XYZ'
import TileState from 'ol/TileState'
import VectorLayer from 'ol/layer/Vector'
import VectorSource from 'ol/source/Vector'
import Feature from 'ol/Feature'
import Point from 'ol/geom/Point'
import LineString from 'ol/geom/LineString'
import { fromLonLat, toLonLat } from 'ol/proj'
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
import { hexToRgba } from '../lib/color'
import { PHOTO_SIZE, markerZIndex, onPhotoLoaded, photoCanvas, photoImage, ringFor, safePhotoUrl } from '../lib/photoMarker'
import { getWeatherTile } from '../api'
import { createMapShell } from '../platform/map-shell/createMapShell'
import { Z } from '../platform/map-shell/zorder'
import { MODULES } from '../modules'
import { MAP_MODULES } from '../modules/mapEntries'
import { FIRE_MAP_LAYERS } from './map/fireLayerList'
import { LEGACY_FIRE_MAP } from './map/fireLayers'

const DEFAULT_COLOR = '#3b82f6'

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
  { id: 'offline',      label: 'Offline' },
]

const { bgMountainsOffline, resolveBgMountainsDefault } = useSettings()

function makeBgMountainsSource() {
  if (bgMountainsOffline.value) {
    return new XYZ({
      url: '/tiles/bgmountains/{z}/{x}/{y}.png',
      attributions: '© BGMountains',
      wrapX: false,
      minZoom: 7,
      maxZoom: 18,
      transition: 0,
    })
  }

  return new XYZ({
    url: 'https://bgmtile.kade.si/{z}/{x}/{y}.png',
    attributions: '© BGMountains',
    crossOrigin: 'anonymous',
    maxZoom: 18,
  })
}

function makeOfflineSource() {
  // Взимаме името на избраната MBTiles карта от localStorage
  const selectedMap = localStorage.getItem('selectedOfflineMap') || 'default'

  const HOST = import.meta.env.VITE_TILE_HOST;
  const PORT = import.meta.env.VITE_TILE_PORT;

  const TILE_SERVER = `http://${HOST}:${PORT}`;

  return new XYZ({
    // Добавяме параметри против кеширане на стария слой
    url: `${TILE_SERVER}/tiles/{z}/{x}/{y}.jpg?map=${encodeURIComponent(selectedMap)}&t=${Date.now()}`,
    attributions: 'Offline',
    wrapX: false,
    transition: 0, // Изключваме плавното преливане, за да не прозират стари тайлове
  })
}

function makeBasemapLayer(id) {
  let source

  switch (id) {
    default:
    case 'osm':
      source = new OSM()
      break

    case 'dark':
      source = new XYZ({
        url:
          'https://{a-d}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
        attributions: '© CartoDB',
      })
      break

    case 'satellite':
      source = new XYZ({
        url:
          'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attributions: '© Esri',
      })
      break

    case 'topo':
      source = new XYZ({
        url:
          'https://{a-c}.tile.opentopomap.org/{z}/{x}/{y}.png',
        attributions: '© OpenTopoMap',
      })
      break

    case 'bgmountains':
      source = makeBgMountainsSource()
      break

    case 'offline':
      source = makeOfflineSource()
      break
  }

  return new TileLayer({
    source,
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
  let basemapLayer = makeBasemapLayer('osm')
  let checkpointNumbersVisible = false
  let mgrsLabelMode = false
  let latLonGridVisible = false
  let measurePoints = []
  let staleTimer    = null
  let hqLabel = 'ЩАБ'
  // Repeaters have no GNSS: an admin places each one by hand, like HQ.
  let repeaterPlacedCb = null

  // The map shell owns the ol/Map, the layer z-order, the three modes (HQ placement, repeater
  // placement, measuring; first in the list wins) and the click / pointer / context-menu dispatch.
  // It is created here, at set-up, and mounted in onMounted, so every call below that arrives before
  // the map exists (setHQ, setHotspots, setZones, setRepeaters, a mode) keeps working.
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
  const shell = createMapShell({
    view:     new View({ center: fromLonLat([25.0, 42.5]), zoom: 7 }),
    controls: [new ScaleLine({ units: 'metric', bar: false, minWidth: 100 })],
    overlays: [tooltip],
    createLongPress,
    modes:    ['hq-place', 'repeater-place', 'measure'],
    basemap:  basemapLayer,
  })

  // Marker layer
  const source      = new VectorSource()
  const vectorLayer = new VectorLayer({ source })

  // Trail line layer
  const trailSource = new VectorSource()
  const trailLayer  = new VectorLayer({ source: trailSource, visible: false })

  // Checkpoint dot layer
  const checkpointSource = new VectorSource()
  const checkpointLayer  = new VectorLayer({ source: checkpointSource, visible: false })

  // Callbacks of the map's clicks; the fire layers (map/fireLayers.js) reach them through mapCtx.
  let fireClickCb = null
  let trackerClickCb = null
  let contextMenuCb = null

  // Measure layer
  const measureSource = new VectorSource()
  const measureLayer  = new VectorLayer({ source: measureSource })

  // HQ layer
  const hqSource = new VectorSource()
  const hqLayer  = new VectorLayer({ source: hqSource })

  const repeaterSource = new VectorSource()
  const repeaterLayer  = new VectorLayer({ source: repeaterSource })

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
          const m = shell.map
          const center = m?.getView().getCenter()
          if (center) {
            const [, lat] = toLonLat(center)
            const zoom = m.getView().getZoom() ?? 7
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
          const m = shell.map
          const center = m?.getView().getCenter()
          if (center) {
            const [lon] = toLonLat(center)
            const zoom = m.getView().getZoom() ?? 7
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
  })

  // What a contribution (a module's map entry) needs from the facade. Each function reads the facade's
  // callback variable at call time, so a callback set or cleared later (onTrackerClick(null) on
  // unmount) is honoured.
  const trackerHit = (pixel) => !!shell.map?.hasFeatureAtPixel(pixel, { layerFilter: l => l === vectorLayer, hitTolerance: 5 })
  const mapCtx = {
    trackerHit,
    reportTrackerClick: (id) => trackerClickCb?.(id),
    fireClickRegistered: () => !!fireClickCb,
    reportFireClick: (selection) => fireClickCb?.(selection),
    onHQPlaced: (loc) => onHQPlaced?.(loc),
  }

  // Fire (burnt areas, zones, hotspots) is one contribution: its three layers keep their place at the
  // bottom of the stack and its five functions are delegated below. A failed install gives an empty api.
  const fire = shell.install(LEGACY_FIRE_MAP, FIRE_MAP_LAYERS, mapCtx)

  // The map's own layers, in the order they have always been on the map. Their z-index comes from
  // the shell's z-order table; the basemap (first) is the shell's own.
  shell.addLayer({ id: 'graticule',   zIndex: Z.graticule,   layer: graticule })
  shell.addLayer({ id: 'trail',       zIndex: Z.trail,       layer: trailLayer })
  shell.addLayer({ id: 'checkpoints', zIndex: Z.checkpoints, layer: checkpointLayer })
  shell.addLayer({ id: 'repeaters',   zIndex: Z.repeaters,   layer: repeaterLayer })
  shell.addLayer({ id: 'hq',          zIndex: Z.hq,          layer: hqLayer })
  shell.addLayer({ id: 'trackers',    zIndex: Z.trackers,    layer: vectorLayer })
  shell.addLayer({ id: 'measure',     zIndex: Z.measure,     layer: measureLayer })

  let activeBasemapId = 'osm'

  // `recolor(data, width)` (lib/weatherTiles.js) repaints each tile's RGBA bytes in place; without it the
  // provider's tiles are shown as they come.
  function setWeatherLayer(url, recolor = null) {
    const map = shell.map
    if (activeWeatherLayer) {
      map?.removeLayer(activeWeatherLayer)
      activeWeatherLayer = null
    }
    if (!url || !map) return
    const source = new XYZ({ url })
    source.setTileLoadFunction((tile, src) => loadWeatherTile(tile, src, recolor))
    activeWeatherLayer = new TileLayer({ source, opacity: 1.0, zIndex: Z.weather })
    map.addLayer(activeWeatherLayer)
  }

  // Weather tiles come from the backend proxy (/api/weather/tiles, login required). An <img> cannot
  // send the Authorization header, so the tile is fetched through the API client (which also renews
  // an expired token) and handed to OpenLayers as an object URL, freed once the image has loaded.
  function loadWeatherTile(tile, src, recolor) {
    const target = tile.getImage()
    getWeatherTile(src).then((blob) => {
      const objectUrl = URL.createObjectURL(blob)
      const free = () => URL.revokeObjectURL(objectUrl)
      target.addEventListener('load', free, { once: true })
      target.addEventListener('error', free, { once: true })
      if (recolor) loadRecolored(tile, objectUrl, recolor)
      else target.src = objectUrl
    }).catch(() => tile.setState(TileState.ERROR))
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
    if (!shell.map) return
    activeBasemapId = id

    // 1. Изчистваме източника на стария слой от паметта
    if (basemapLayer) {
      const oldSource = basemapLayer.getSource()
      if (oldSource && typeof oldSource.clear === 'function') {
        oldSource.clear()
      }
    }

    // 2. Създаваме новия слой (който ще извика обновения makeOfflineSource()) и го слагаме на мястото
    //    на стария (първи слой на картата)
    basemapLayer = makeBasemapLayer(id)
    shell.setBasemap(basemapLayer)
  }

  watch(bgMountainsOffline, () => {
    if (activeBasemapId === 'bgmountains') setBasemap('bgmountains')
  })

  function forceGraticuleRedraw() {
    graticule.renderedExtent_ = null
    shell.map?.render()
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

  // Hover: tooltip of the tracker under the pointer, pointer cursor, coordinate read-out. Runs in every mode.
  shell.onPointerMove((evt) => {
    const map = shell.map
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
  }, { always: true, order: 10 })

  // Placement modes: the click reports where, nothing else happens.
  shell.onClick((evt) => {
    const [lon, lat] = toLonLat(evt.coordinate)
    mapCtx.onHQPlaced({ lat, lon })
    return true
  }, { mode: 'hq-place' })
  shell.onClick((evt) => {
    const [lon, lat] = toLonLat(evt.coordinate)
    repeaterPlacedCb?.({ lat, lon })
    return true
  }, { mode: 'repeater-place' })

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

  shell.onClick((evt) => {
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
    return true
  }, { mode: 'measure' })

  // A tracker click opens the tracker popup and closes any fire popup (the fire click handler, order 20,
  // is in map/fireLayers.js; this one runs first and stops the click).
  shell.onClick((evt) => {
    if (!mapCtx.fireClickRegistered()) return false
    if (!mapCtx.trackerHit(evt.pixel)) return false
    mapCtx.reportFireClick(null)
    const marker = shell.map.forEachFeatureAtPixel(evt.pixel, f => f, { layerFilter: l => l === vectorLayer, hitTolerance: 5 })
    if (marker && marker.getId() != null) mapCtx.reportTrackerClick(String(marker.getId()))
    return true
  }, { order: 10 })

  // "Report fire here": right-click on a mouse, long-press on touch. Both hand over the clicked
  // coordinate (EPSG:3857) and its pixel inside the map element; the view decides what to offer.
  // The shell reports one gesture once and not while a mode is active.
  shell.onContextMenu(({ coordinate, pixel }) => contextMenuCb?.({ coordinate, pixel }))

  // Modules' map entries (none yet): their layers sit after the map's own.
  for (const entry of MAP_MODULES) {
    const declarations = MODULES.find(m => m.name === entry.name)?.mapLayers ?? []
    shell.install(entry, declarations, mapCtx)
  }

  onMounted(() => {
    resolveBgMountainsDefault()   // offline BG Mountains tiles only if this server has them (useSettings.js)
    shell.mount(mapRef.value)

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
    shell.dispose()
    clearInterval(staleTimer)
  })

  function setMeasureMode(on) {
    if (!on) {
      measurePoints = []
      measureSource.clear()
      onMeasure?.(null)
    }
    shell.setMode('measure', on)
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
    shell.setMode('hq-place', on)
  }

  function makeRepeaterStyle(label, active) {
    const color = active ? '#22d3ee' : '#64748b'
    return new Style({
      image: new RegularShape({
        points:  3,
        radius:  11,
        angle:   0,
        fill:    new Fill({ color }),
        stroke:  new Stroke({ color: '#000', width: 2 }),
      }),
      text: new Text({
        text:    label,
        offsetY: -18,
        font:    'bold 12px system-ui',
        fill:    new Fill({ color }),
        stroke:  new Stroke({ color: '#000', width: 3 }),
      }),
    })
  }

  // Repeaters arrive as device rows; only placed ones (site_latitude/site_longitude set) are drawn.
  // An inactive repeater stays on the map, greyed, so its spot is not forgotten.
  function setRepeaters(list) {
    repeaterSource.clear(true)
    for (const d of Array.isArray(list) ? list : []) {
      const lat = Number(d?.site_latitude), lon = Number(d?.site_longitude)
      if (d?.site_latitude == null || !Number.isFinite(lat) || !Number.isFinite(lon)) continue
      const f = new Feature({ geometry: new Point(fromLonLat([lon, lat])) })
      f.setId(`repeater:${d.id}`)
      f.setStyle(makeRepeaterStyle(d.name || `R${d.dev_sn}`, d.is_active !== false))
      repeaterSource.addFeature(f)
    }
  }

  function setRepeaterPlacementMode(on) {
    shell.setMode('repeater-place', on)
  }
  function onRepeaterPlaced(cb) { repeaterPlacedCb = cb }

  // Fire functions: delegated to the fire contribution (map/fireLayers.js). They work before the map
  // is mounted. When its install failed the api is empty: the two GeoJSON setters report false (the
  // pill then shows the feed as failed, which is true) and the other three do nothing.
  const setBurntAreas      = (fc)      => fire.setBurntAreas?.(fc) ?? false
  const setHotspots        = (fc)      => fire.setHotspots?.(fc) ?? false
  const setZones           = (list)    => fire.setZones?.(list)
  const setFireLayerVisible = (n, v)   => { fire.setFireLayerVisible?.(n, v) }
  const setFireLabels      = (labels)  => { fire.setFireLabels?.(labels) }

  function onFireFeatureClick(cb) { fireClickCb = cb }
  // A click on a tracker marker passes its device id; a click on bare map passes null.
  function onTrackerClick(cb) { trackerClickCb = cb }
  function onMapContextMenu(cb) { contextMenuCb = cb }

  function refreshMarkers(list) {
    list.forEach(safeUpsert)
    removeStaleFeatures(list.map(p => p.device_id))
  }

  return { map: () => shell.map, setBasemap, setMGRSGrid, setLatLonGrid, setTrailVisible, setCheckpointNumbers, setMeasureMode, setWeatherLayer, refreshMarkers, setHQ, setHQPlacementMode, setRepeaters, setRepeaterPlacementMode, onRepeaterPlaced, setBurntAreas, setHotspots, setFireLayerVisible, setFireLabels, onFireFeatureClick, setZones, onTrackerClick, onMapContextMenu }
}
