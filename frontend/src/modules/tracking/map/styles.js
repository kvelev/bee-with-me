// Marker, photo-marker, trail and checkpoint styles of the tracking map entry (moved from useMap.js, T632).
// useMap.js re-exports makeMarkerStyle and makePhotoMarkerStyle.
import { Circle, Fill, Stroke, Style, Text } from 'ol/style'
import Icon from 'ol/style/Icon'
import { LIVE, LOST } from '../lib/freshness.js'
import { PHOTO_SIZE, markerZIndex, photoCanvas, photoImage, ringFor } from '../lib/photoMarker.js'
import { hexToRgba } from '../../../lib/color.js'

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

export function makeTrailStyle(color) {
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

export function makeCheckpointStyle(color, index, isLast, showLabels, recordedAt) {
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
