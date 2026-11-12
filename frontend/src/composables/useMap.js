import { onMounted, onUnmounted, ref, watch } from 'vue'
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
import Graticule from 'ol/layer/Graticule'
import ScaleLine from 'ol/control/ScaleLine'
import { forward as toMGRS } from 'mgrs'
import { useSettings } from './useSettings'
import { createLongPress } from '../lib/longPress'
import { getWeatherTile } from '../api'
import { createMapShell } from '../platform/map-shell/createMapShell'
import { Z } from '../platform/map-shell/zorder'
import { MODULES } from '../modules'
import { MAP_MODULES } from '../modules/mapEntries'
import { makeMarkerStyle, makePhotoMarkerStyle } from '../modules/tracking/map/styles'

// The marker styles live in the tracking map entry; they stay importable from here.
export { makeMarkerStyle, makePhotoMarkerStyle }

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

export function useMap(mapRef, positionList, trails, onCursorMGRS, onMeasure, groupsMap, onHQPlaced, showPhotos = ref(true)) {
  let basemapLayer = makeBasemapLayer('osm')
  let mgrsLabelMode = false
  let latLonGridVisible = false
  let measurePoints = []
  // Repeaters have no GNSS: an admin places each one by hand, like HQ.
  let repeaterPlacedCb = null

  // The map shell owns the ol/Map, the layer z-order, the three modes (HQ placement, repeater
  // placement, measuring; first in the list wins) and the click / pointer / context-menu dispatch.
  // It is created here, at set-up, and mounted in onMounted, so every call below that arrives before
  // the map exists (setHQ, setHotspots, setZones, setRepeaters, a mode) keeps working.
  const shell = createMapShell({
    view:     new View({ center: fromLonLat([25.0, 42.5]), zoom: 7 }),
    controls: [new ScaleLine({ units: 'metric', bar: false, minWidth: 100 })],
    overlays: [],
    createLongPress,
    modes:    ['hq-place', 'repeater-place', 'measure'],
    basemap:  basemapLayer,
  })

  // Callbacks of the map's clicks; the fire layers (modules/fire/map/index.js) reach them through mapCtx.
  let fireClickCb = null
  let trackerClickCb = null
  let contextMenuCb = null

  // Measure layer
  const measureSource = new VectorSource()
  const measureLayer  = new VectorLayer({ source: measureSource })

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
  // The tracker layer is the tracking entry's; without it (its install failed) no tracker is ever under the pointer.
  const moduleApis = {}
  const mapCtx = {
    trackerHit: (pixel) => moduleApis.tracking?.trackerHit?.(pixel) ?? false,
    reportTrackerClick: (id) => trackerClickCb?.(id),
    fireClickRegistered: () => !!fireClickCb,
    reportFireClick: (selection) => fireClickCb?.(selection),
    onHQPlaced: (loc) => onHQPlaced?.(loc),
  }

  // The map's own layers, in the order they have always been on the map. Their z-index comes from
  // the shell's z-order table; the basemap (first) is the shell's own.
  shell.addLayer({ id: 'graticule',   zIndex: Z.graticule,   layer: graticule })
  shell.addLayer({ id: 'repeaters',   zIndex: Z.repeaters,   layer: repeaterLayer })
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

  // Cursor coordinate read-out. Runs in every mode. (The tracker tooltip is the tracking entry's.)
  shell.onPointerMove((evt) => {
    // cursor coordinate readout
    if (onCursorMGRS) {
      try {
        const [lon, lat] = toLonLat(evt.coordinate)
        onCursorMGRS({ mgrs: toMGRS([lon, lat], 5), lat, lon })
      } catch {
        onCursorMGRS(null)
      }
    }
  }, { always: true, order: 20 })

  // Repeater placement mode: the click reports where, nothing else happens. (HQ placement is the settings
  // module's: modules/settings/map/index.js.)
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

  // "Report fire here": right-click on a mouse, long-press on touch. Both hand over the clicked
  // coordinate (EPSG:3857) and its pixel inside the map element; the view decides what to offer.
  // The shell reports one gesture once and not while a mode is active.
  shell.onContextMenu(({ coordinate, pixel }) => contextMenuCb?.({ coordinate, pixel }))

  // Modules' map entries: their layers sit after the map's own (the z-index decides what is drawn on top).
  // An entry whose install failed has an empty api; the names delegated below then do nothing.
  for (const entry of MAP_MODULES) {
    const declarations = MODULES.find(m => m.name === entry.name)?.mapLayers ?? []
    moduleApis[entry.name] = shell.install(entry, declarations, mapCtx)
  }

  onMounted(() => {
    resolveBgMountainsDefault()   // offline BG Mountains tiles only if this server has them (useSettings.js)
    shell.mount(mapRef.value)

  })

  // The tracking module's map entry draws the people. Its api is read at call time: when its install failed
  // it is empty, nothing is drawn, and refreshMarkers says so (the view then shows a note, BP-03).
  const trackingApi = () => moduleApis.tracking ?? {}
  trackingApi().setGroups?.(groupsMap?.value)
  trackingApi().setShowPhotos?.(showPhotos.value)   // the entry starts with the photos on; the setting may say otherwise
  watch(() => groupsMap?.value, (g) => trackingApi().setGroups?.(g), { deep: true })

  watch(positionList, (list) => { trackingApi().setPositions?.(list) }, { deep: true })

  // The setting changed: redraw every marker now.
  watch(showPhotos, (on) => {
    trackingApi().setPositions?.(positionList.value ?? [])
    trackingApi().setShowPhotos?.(on)
  })

  watch(trails, (trailMap) => { trackingApi().setTrails?.(trailMap) }, { deep: true })

  onUnmounted(() => {
    shell.dispose()   // the tracking entry stops its timer and its photo-restyle listener here
  })

  function setMeasureMode(on) {
    if (!on) {
      measurePoints = []
      measureSource.clear()
      onMeasure?.(null)
    }
    shell.setMode('measure', on)
  }

  // HQ: delegated to the settings module's map entry. Without it (its install failed) the two names are
  // no-ops that log once, so the rest of the map keeps working (BP-03).
  let hqMissingLogged = false
  function settingsMapFn(name) {
    const fn = moduleApis.settings?.[name]
    if (typeof fn === 'function') return fn
    return () => {
      if (hqMissingLogged) return
      hqMissingLogged = true
      console.error('map: the settings module is not on the map, %s does nothing', name)
    }
  }
  const setHQ = (loc, label) => settingsMapFn('setHQ')(loc, label)
  // true when the settings entry handled the call, false when it is missing (T580: the view shows it).
  const setHQPlacementMode = (on) => {
    const handled = typeof moduleApis.settings?.setHQPlacementMode === 'function'
    settingsMapFn('setHQPlacementMode')(on)
    return handled
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

  // Fire functions: delegated to the fire module's map entry (modules/fire/map/index.js), read from
  // moduleApis at call time so they work before the map is mounted. When its install failed the api is
  // empty: the two GeoJSON setters report false (the pill then shows the feed as failed, which is true)
  // and the other three do nothing.
  const fireApi = () => moduleApis.fire ?? {}
  const setBurntAreas      = (fc)      => fireApi().setBurntAreas?.(fc) ?? false
  const setHotspots        = (fc)      => fireApi().setHotspots?.(fc) ?? false
  const setZones           = (list)    => fireApi().setZones?.(list)
  const setFireLayerVisible = (n, v)   => { fireApi().setFireLayerVisible?.(n, v) }
  const setFireLabels      = (labels)  => { fireApi().setFireLabels?.(labels) }

  function onFireFeatureClick(cb) { fireClickCb = cb }
  // A click on a tracker marker passes its device id; a click on bare map passes null.
  function onTrackerClick(cb) { trackerClickCb = cb }
  function onMapContextMenu(cb) { contextMenuCb = cb }

  // true when the tracking entry drew the list, false when it is missing (its install failed).
  function refreshMarkers(list) {
    return trackingApi().refreshMarkers?.(list) ?? false
  }

  const setTrailVisible = (visible) => { trackingApi().setTrailVisible?.(visible) }
  const setCheckpointNumbers = (visible) => { trackingApi().setCheckpointNumbers?.(visible) }

  return { map: () => shell.map, setBasemap, setMGRSGrid, setLatLonGrid, setTrailVisible, setCheckpointNumbers, setMeasureMode, setWeatherLayer, refreshMarkers, setHQ, setHQPlacementMode, setRepeaters, setRepeaterPlacementMode, onRepeaterPlaced, setBurntAreas, setHotspots, setFireLayerVisible, setFireLabels, onFireFeatureClick, setZones, onTrackerClick, onMapContextMenu }
}
