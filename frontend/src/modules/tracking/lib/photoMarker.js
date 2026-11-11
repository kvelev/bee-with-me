// Round photo markers for the live map (F1). Pure helpers plus a per-URL image cache; the
// OpenLayers style itself is assembled in useMap.js.
//
// The ring keeps every state the plain dot shows (BP-01): SOS red and thicker, stale and lost
// grey with a fainter photo, no GNSS fix yellow and dashed, otherwise the group colour.
// No glow anywhere: glow is an alarm signal.

import { LIVE, LOST } from './freshness'
import { hexToRgba } from '../../../lib/color'

export const PHOTO_SIZE = 34   // outer diameter in CSS px, ring included

const SOS_RED = '#ef4444'
const NO_FIX  = '#facc15'
const GREY    = '#9ca3af'

/** Same-origin photo URL or null. A photo is only ever loaded from this server (TP-01): an
 *  absolute URL to another host, a protocol-relative one and any data:/javascript: URL are
 *  refused, and the map keeps the dot. */
export function safePhotoUrl(raw, origin = globalThis.location?.origin) {
  if (typeof raw !== 'string' || !raw.trim() || !origin) return null
  try {
    const u = new URL(raw.trim(), origin)
    if (u.origin !== origin) return null
    return u.pathname + u.search
  } catch {
    return null
  }
}

/** Draw order on the marker layer: SOS above everything, then live, stale, lost (B54). */
export function markerZIndex(isSOS, freshness) {
  if (isSOS) return 40
  return freshness === LOST ? 10 : freshness === LIVE ? 30 : 20
}

/** Ring and photo opacity for one marker state. */
export function ringFor({ color, isSOS, freshness, noFix }) {
  const photoAlpha = freshness === LOST ? 0.3 : freshness === LIVE ? 1 : 0.55
  if (isSOS) {
    // Red stays reserved for SOS; a dashed red ring says "SOS, and no satellite fix". An SOS from
    // a tracker that went quiet keeps the red ring but dims the photo and gets a grey inner ring,
    // so it never looks live (BP-01).
    const quiet = freshness !== LIVE
    return { color: SOS_RED, width: 5, dash: noFix ? [5, 3] : null, photoAlpha: quiet ? photoAlpha : 1,
             innerColor: quiet ? hexToRgba(GREY, 0.9) : null }
  }
  const base = freshness === LOST ? hexToRgba(GREY, 0.4)
    : freshness !== LIVE ? hexToRgba(GREY, 0.8)
    : color
  return { color: noFix ? NO_FIX : base, width: 3, dash: noFix ? [5, 3] : null, photoAlpha }
}

// ---- image cache -------------------------------------------------------------------------

const MAX_CACHED_CANVASES = 400
const RETRY_BASE_MS = 60_000
const RETRY_MAX_MS = 10 * 60_000
const images = new Map()     // url -> { state: 'loading' | 'ready' | 'failed', img, failures, retryAt }
const canvases = new Map()   // ring/url/dpr key -> canvas
const listeners = new Set()  // every live map instance that wants to hear about a finished load

function startLoad(url, entry) {
  const img = new Image()
  entry.state = 'loading'
  entry.img = img
  img.onload  = () => { entry.state = 'ready'; entry.failures = 0; for (const fn of [...listeners]) fn() }
  img.onerror = () => {
    entry.state = 'failed'
    entry.failures = (entry.failures ?? 0) + 1
    entry.retryAt = Date.now() + Math.min(RETRY_MAX_MS, RETRY_BASE_MS * 2 ** (entry.failures - 1))
  }
  img.src = url
}

/** Subscribe to "an image finished loading". Returns the unsubscribe function (call it on
 *  unmount): every open map restyles, not only the one that started the load. */
export function onPhotoLoaded(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

/** The decoded image for `url` when ready, else null. The first call starts the load; a finished
 *  load notifies every subscriber (`onPhotoLoaded`). A failure is silent
 *  (no console output, nothing with a name or URL in it): the marker stays a dot, and the URL is
 *  tried again after a backoff (60 s, doubling, capped at 10 min) the next time a marker asks. */
export function photoImage(url, now = Date.now()) {
  let entry = images.get(url)
  if (!entry) {
    entry = { failures: 0 }
    images.set(url, entry)
    startLoad(url, entry)
  } else if (entry.state === 'failed' && now >= entry.retryAt) {
    startLoad(url, entry)
  }
  return entry.state === 'ready' ? entry.img : null
}

export function clearPhotoCache() { images.clear(); canvases.clear() }

/** A circular canvas: clipped photo, ring on the outer edge. Null when no 2D context exists. */
export function photoCanvas(url, img, ring, dpr = 1) {
  const key = `${url}|${ring.color}|${ring.width}|${ring.dash ?? ''}|${ring.photoAlpha}|${ring.innerColor ?? ''}|${dpr}`
  const hit = canvases.get(key)
  if (hit) return hit
  const px = Math.round(PHOTO_SIZE * dpr)
  const canvas = document.createElement('canvas')
  canvas.width = px
  canvas.height = px
  const ctx = canvas.getContext?.('2d')
  if (!ctx) return null
  ctx.scale(dpr, dpr)
  const r = PHOTO_SIZE / 2
  const inner = r - ring.width
  const iw = img.naturalWidth || img.width || 1
  const ih = img.naturalHeight || img.height || 1
  const side = Math.min(iw, ih)   // centre-crop to a square
  ctx.save()
  ctx.beginPath()
  ctx.arc(r, r, inner, 0, Math.PI * 2)
  ctx.clip()
  ctx.globalAlpha = ring.photoAlpha
  ctx.drawImage(img, (iw - side) / 2, (ih - side) / 2, side, side, r - inner, r - inner, inner * 2, inner * 2)
  ctx.restore()
  if (ring.innerColor) {   // grey inner ring: this SOS is not live
    ctx.beginPath()
    ctx.arc(r, r, inner - 1, 0, Math.PI * 2)
    ctx.lineWidth = 2
    ctx.strokeStyle = ring.innerColor
    ctx.setLineDash?.([])
    ctx.stroke()
  }
  ctx.beginPath()
  ctx.arc(r, r, r - ring.width / 2, 0, Math.PI * 2)
  ctx.lineWidth = ring.width
  ctx.strokeStyle = ring.color
  ctx.setLineDash?.(ring.dash ?? [])
  ctx.stroke()
  if (canvases.size >= MAX_CACHED_CANVASES) canvases.clear()
  canvases.set(key, canvas)
  return canvas
}
