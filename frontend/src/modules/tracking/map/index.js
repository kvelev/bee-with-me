// The tracking module's map entry: the tracker, trail and checkpoint layers, their styles, the tooltip, the
// tracker click and the 60 second stale timer (moved from useMap.js, T632). It is a map contribution in the
// shape of createMapShell's `install` (layers by declared id, then `setup`). It may import ol/*; the manifest
// (../index.js) never does.
import Overlay from 'ol/Overlay'
import VectorLayer from 'ol/layer/Vector'
import VectorSource from 'ol/source/Vector'
import Feature from 'ol/Feature'
import Point from 'ol/geom/Point'
import LineString from 'ol/geom/LineString'
import { fromLonLat } from 'ol/proj'
import { normaliseGroups } from '../../../lib/groups.js'
import { freshnessOf } from '../lib/freshness.js'
import { renderTrackerTooltip } from '../lib/trackerTooltip.js'
import { onPhotoLoaded, safePhotoUrl } from '../lib/photoMarker.js'
import { TRACKING_CHECKPOINTS_LAYER, TRACKING_TRAIL_LAYER, TRACKING_TRACKERS_LAYER } from './layers.js'
import { makeCheckpointStyle, makeMarkerStyle, makePhotoMarkerStyle, makeTrailStyle } from './styles.js'

export { makeMarkerStyle, makePhotoMarkerStyle }

const DEFAULT_COLOR = '#3b82f6'
const STALE_CHECK_MS = 60_000

function createTooltip() {
  const element = document.createElement('div')
  Object.assign(element.style, {
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
  return {
    element,
    overlay: new Overlay({ element, offset: [14, 0], positioning: 'center-left', stopEvent: false }),
  }
}

const createTrailLayer = () => new VectorLayer({ source: new VectorSource(), visible: false })
const createCheckpointLayer = () => new VectorLayer({ source: new VectorSource(), visible: false })
const createTrackerLayer = () => new VectorLayer({ source: new VectorSource() })

function setupTrackingMap(shell, ctx) {
  const trailLayer = shell.layer(TRACKING_TRAIL_LAYER.id)
  const checkpointLayer = shell.layer(TRACKING_CHECKPOINTS_LAYER.id)
  const trackerLayer = shell.layer(TRACKING_TRACKERS_LAYER.id)
  if (!trailLayer || !checkpointLayer || !trackerLayer) throw new Error('a tracking layer is not registered')
  const trailSource = trailLayer.getSource()
  const checkpointSource = checkpointLayer.getSource()
  const source = trackerLayer.getSource()

  let positions = []
  let groupsMap = {}
  let showPhotos = true
  let checkpointNumbersVisible = false
  let staleTimer = null
  let restyleHandle = null
  let restyleViaRaf = false
  let live = true
  const cleanups = []
  const dispose = () => {
    live = false
    for (const fn of cleanups.splice(0).reverse()) {
      try { fn() } catch (error) { console.error('tracking map cleanup failed', error?.message ?? error) }
    }
  }

  try {
    const tooltip = createTooltip()

    // One place decides how a marker looks. Photo only for an individual (never the team dot in
    // the groups view) with the setting on and a same-origin photo that has loaded; every other
    // case, including a failed load, is the dot.
    const styleFor = (pos) => {
      const leaderGroup = pos.groups?.find(g => g.is_leader)
      const color     = leaderGroup?.color ?? pos.groups?.[0]?.color ?? DEFAULT_COLOR
      const freshness = freshnessOf(pos)
      const noFix     = pos.gnss_valid === false
      const isTeam    = !!pos.displayLabel
      const label     = pos.displayLabel || pos.full_name || pos.device_name || String(pos.dev_sn ?? '')
      if (!isTeam && showPhotos !== false) {
        const url = safePhotoUrl(pos.photo_url)
        const photo = url && makePhotoMarkerStyle(url, color, pos.sos_active, label, freshness, noFix)
        if (photo) return photo
      }
      return makeMarkerStyle(color, pos.sos_active, label, isTeam, freshness, noFix)
    }

    const restyleAll = () => {
      source.getFeatures().forEach(f => {
        const pos = f.get('pos')
        if (pos) f.setStyle(styleFor(pos))
      })
    }

    // Photos finish loading in separate tasks, so a microtask would not merge them (N restyles of N
    // markers on start). One restyle per animation frame (50 ms timer where there is no rAF) covers
    // every photo that arrived meanwhile (B56).
    const scheduleRestyle = () => {
      if (restyleHandle != null) return
      const run = () => { restyleHandle = null; restyleAll() }
      restyleViaRaf = typeof requestAnimationFrame === 'function'
      restyleHandle = restyleViaRaf ? requestAnimationFrame(run) : setTimeout(run, 50)
    }
    // Every open map hears about every finished photo, not only the one that started the load.
    cleanups.push(onPhotoLoaded(scheduleRestyle))
    cleanups.push(() => {
      if (restyleHandle == null) return
      restyleViaRaf ? cancelAnimationFrame(restyleHandle) : clearTimeout(restyleHandle)
      restyleHandle = null
    })

    const upsertFeature = (rawPos) => {
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

    // One malformed row must never blank every marker (B50): isolate each upsert.
    const safeUpsert = (pos) => {
      try { upsertFeature(pos) } catch { console.warn('Skipped a position that could not be drawn') }
    }

    const removeStaleFeatures = (currentIds) => {
      const set = new Set(currentIds)
      source.getFeatures().forEach(f => {
        if (!set.has(f.getId())) source.removeFeature(f)
      })
    }

    function setPositions(list) {
      positions = Array.isArray(list) ? list : []
      positions.forEach(safeUpsert)
      removeStaleFeatures(positions.map(p => p.device_id))
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

    const removeStaleTrails = (currentIds) => {
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

    const removeStaleCheckpoints = (currentIds) => {
      const set = new Set(currentIds)
      checkpointSource.getFeatures()
        .filter(f => !set.has(f.get('deviceId')))
        .forEach(f => checkpointSource.removeFeature(f))
    }

    function setTrails(trailMap) {
      const trails = trailMap ?? {}
      Object.entries(trails).forEach(([deviceId, points]) => {
        upsertTrail(deviceId, points)
        upsertCheckpoints(deviceId, points)
      })
      removeStaleTrails(Object.keys(trails))
      removeStaleCheckpoints(Object.keys(trails))
    }

    function setGroups(map) { groupsMap = map ?? {} }

    // The setting changed: restyle every marker now (the caller has handed over the current list first).
    function setShowPhotos(on) {
      showPhotos = on
      restyleAll()
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

    // Draws a list now and remembers it for the tooltip; the facade's refreshMarkers.
    function refreshMarkers(list) {
      setPositions(list)
      return true
    }

    const trackerHit = (pixel) => !!shell.map?.hasFeatureAtPixel(pixel, { layerFilter: l => l === trackerLayer, hitTolerance: 5 })
    const markerAt = (pixel) => shell.map.forEachFeatureAtPixel(pixel, f => f, { layerFilter: l => l === trackerLayer, hitTolerance: 5 })

    // Hover: tooltip of the tracker under the pointer and the pointer cursor. Runs in every mode.
    cleanups.push(shell.onPointerMove((evt) => {
      const map = shell.map
      const feature = markerAt(evt.pixel)
      if (feature) {
        const stored = feature.get('pos')
        const pos    = positions.find(p => p.device_id === feature.getId()) ?? stored
        const leaderGroup = pos.displayLabel ? pos.groups?.find(g => g.is_leader) : null
        const gDetail     = leaderGroup ? groupsMap[leaderGroup.id] : null
        renderTrackerTooltip(tooltip.element, pos, gDetail, { showPhotos: showPhotos !== false })
        tooltip.element.style.display = 'block'
        tooltip.overlay.setPosition(evt.coordinate)
        map.getTargetElement().style.cursor = 'pointer'
      } else {
        tooltip.element.style.display = 'none'
        tooltip.overlay.setPosition(undefined)
        map.getTargetElement().style.cursor = ''
      }
    }, { always: true, order: 10, id: 'tracking-tooltip' }))

    // A tracker click opens the tracker popup and closes any fire popup (the fire click handler, order 20,
    // is in modules/fire/map/index.js; this one runs first and stops the click).
    cleanups.push(shell.onClick((evt) => {
      if (!ctx.fireClickRegistered()) return false
      if (!trackerHit(evt.pixel)) return false
      ctx.reportFireClick(null)
      const marker = markerAt(evt.pixel)
      if (marker && marker.getId() != null) ctx.reportTrackerClick(String(marker.getId()))
      return true
    }, { order: 10, id: 'tracking-click' }))

    // The tooltip overlay and the stale timer exist while the map does. Re-evaluate stale state every
    // minute without needing a new WS frame.
    shell.onMounted(() => {
      if (!live) return
      shell.map.addOverlay(tooltip.overlay)
      staleTimer = setInterval(restyleAll, STALE_CHECK_MS)
    })
    cleanups.push(() => {
      if (staleTimer != null) clearInterval(staleTimer)
      staleTimer = null
      shell.map?.removeOverlay(tooltip.overlay)
      tooltip.element.style.display = 'none'
    })

    return {
      api: {
        setPositions, setTrails, setGroups, setShowPhotos, setTrailVisible, setCheckpointNumbers,
        refreshMarkers, trackerHit,
      },
      dispose,
    }
  } catch (error) {
    dispose()
    throw error
  }
}

export default {
  name: 'tracking',
  layers: {
    [TRACKING_TRAIL_LAYER.id]: createTrailLayer,
    [TRACKING_CHECKPOINTS_LAYER.id]: createCheckpointLayer,
    [TRACKING_TRACKERS_LAYER.id]: createTrackerLayer,
  },
  setup: setupTrackingMap,
}
