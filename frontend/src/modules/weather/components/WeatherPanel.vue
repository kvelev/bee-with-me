<template>
  <!-- Wind particle canvas -->
  <canvas v-if="weatherUi.layerId === 'wind_new'" ref="windCanvas" class="wind-canvas" />

  <!-- Weather info panel -->
  <div v-if="weatherUi.layerId && weatherInfo" class="weather-panel">
    <div class="weather-header">
      <img :src="`https://openweathermap.org/img/wn/${weatherInfo.icon}@2x.png`" class="weather-icon" alt="" />
      <div>
        <div class="weather-temp">{{ weatherInfo.temp }}°C <span class="weather-feels">{{ t('map.weatherFeels') }} {{ weatherInfo.feelsLike }}°C</span></div>
        <div class="weather-desc">{{ weatherInfo.desc }}</div>
      </div>
    </div>
    <div class="weather-rows">
      <div class="weather-row">
        <span class="weather-label">{{ t('map.weatherWind') }}</span>
        <span class="weather-wind">
          <span class="wind-arrow" :style="{ transform: `rotate(${(weatherInfo.windDeg ?? 0) + 180}deg)` }" aria-hidden="true">↑</span>
          {{ weatherInfo.windSpeed.toFixed(1) }} m/s
          <template v-if="weatherInfo.windDir">{{ t('map.weatherFrom', { dir: weatherInfo.windDir, deg: Math.round(weatherInfo.windDeg ?? 0) }) }}</template>
        </span>
      </div>
      <div v-if="weatherInfo.windGust != null" class="weather-row"><span class="weather-label">{{ t('map.weatherGusts') }}</span><span>{{ weatherInfo.windGust.toFixed(1) }} m/s</span></div>
      <div class="weather-row"><span class="weather-label">{{ t('map.weatherHumidity') }}</span><span>{{ weatherInfo.humidity }}%</span></div>
      <div class="weather-row"><span class="weather-label">{{ t('map.weatherClouds') }}</span><span>{{ weatherInfo.clouds }}%</span></div>
      <div v-if="weatherInfo.city" class="weather-row weather-city">{{ weatherInfo.city }}</div>
      <div v-if="weatherUi.layerId === 'wind_new' && windSourceLabel" class="weather-row weather-city">{{ t('map.weatherWindSource', { source: windSourceLabel }) }}</div>
    </div>
    <div v-if="activeWeatherLayer" class="weather-legend">
      <div class="legend-bar" :style="{ background: activeWeatherLayer.gradient }" />
      <div class="legend-stops">
        <span v-for="s in activeWeatherLayer.stops" :key="s">{{ s }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
// The weather part of the map: the overlay switch (tile layer through context.facade), the info panel, the legend
// and the wind particle animation. The buttons live in WeatherToolbar and flip useWeatherUi().layerId; this panel
// reacts to it. The map is context.hostMap (a shallowRef); OpenLayers helpers come only from context.mapKit.
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { getWeatherBox, getWeatherCurrent } from '../../../api'
import { recolorFor } from '../lib/weatherTiles.js'
import { compassFrom, windPoint, gridPoints, openMeteoUrl, parseOpenMeteo, nearestPoint } from '../lib/wind.js'
import { WEATHER_LAYERS } from '../layers.js'
import { useWeatherUi } from '../ui.js'

const props = defineProps({ context: { type: Object, required: true } })

const { t } = useI18n()
const weatherUi = useWeatherUi()
const { toLonLat, fromLonLat, unByKey } = props.context.mapKit

const map = () => props.context.hostMap.value

const weatherInfo     = ref(null)
let   weatherTimer    = null
const activeWeatherLayer = computed(() => WEATHER_LAYERS.find(l => l.id === weatherUi.layerId) ?? null)

// ── Overlay switch ───────────────────────────────────────────────────────────
watch(() => weatherUi.layerId, async (id) => {
  const url = id ? `/api/weather/tiles/${id}/{z}/{x}/{y}.png` : null
  props.context.facade.setWeatherLayer(url, recolorFor(id))
  if (!id) weatherInfo.value = null
  else if (id !== 'wind_new') fetchWeather()

  stopWindAnim()
  if (id === 'wind_new') {
    await nextTick()
    startWindAnim()
    fetchWindField()
  }
})

// The overlay is only for the satellite basemap (and the offline one, which also lets a layer go on).
// Any other basemap switches it off.
watch(() => props.context.activeBasemap.value, (id) => {
  if (id !== 'satellite' && weatherUi.layerId) weatherUi.layerId = null
})

// ── Map listener ─────────────────────────────────────────────────────────────
let attachedMap = null
function scheduleWeatherFetch() {
  if (!weatherUi.layerId) return
  clearTimeout(weatherTimer)
  weatherTimer = setTimeout(
    () => weatherUi.layerId === 'wind_new' ? fetchWindField() : fetchWeather(),
    700
  )
}
function detachMap() {
  if (attachedMap) attachedMap.un('moveend', scheduleWeatherFetch)
  attachedMap = null
}
watch(() => props.context.hostMap.value, (m) => {
  detachMap()
  if (m) { m.on('moveend', scheduleWeatherFetch); attachedMap = m }
}, { immediate: true })

async function fetchWeather() {
  if (!weatherUi.layerId) return
  const m = map()
  if (!m) return
  const [lon, lat] = toLonLat(m.getView().getCenter())
  try {
    weatherInfo.value = weatherFromOwm(await getWeatherCurrent(+lat.toFixed(4), +lon.toFixed(4)))
  } catch { /* network unavailable, or weather not configured on the server */ }
}

function windDirLabel(deg) {
  return compassFrom(deg)
}

// ── Wind particle animation ──────────────────────────────────────────────────
const windCanvas     = ref(null)
const PARTICLE_COUNT = 180
const TRAIL_LEN      = 10
const SPEED_SCALE    = 45      // px/s per m/s
const GRID_COLS      = 14
const GRID_ROWS      = 9
// Open-Meteo sample grid over the (padded) view: 20 points in one keyless request.
const SAMPLE_COLS    = 5
const SAMPLE_ROWS    = 4
let   windParticles  = []
let   windAnimFrame  = null
let   windLastTime   = null
let   windField      = []      // [{lat,lon,deg,speed,vxNorm,vyNorm}] (lib/wind.js windPoint)
let   windGrid       = null    // GRID_ROWS × GRID_COLS [{vx,vy}] in px/s
let   windMarks      = []      // measured points in canvas pixels, drawn as arrows
let   windGridDirty  = false   // the view moved: rebuild grid and arrows on the next frame
let   windViewKey    = null
let   windFetchSeq   = 0
// box/city needs a paid OWM plan. After a 401/403 it is not asked again this session, so the free
// tier does not pay a failed request on every pan. The code path stays for when the plan allows it.
let   boxCityDenied  = false
const windSource     = ref(null)   // 'owm-box' | 'open-meteo' | 'owm-point'
const windSourceLabel = computed(() => ({
  'owm-box': 'OpenWeatherMap', 'open-meteo': 'Open-Meteo.com', 'owm-point': 'OpenWeatherMap (1 point)',
})[windSource.value] ?? '')

function weatherFromOwm(c) {
  return {
    temp:      Math.round(c.main.temp),
    feelsLike: Math.round(c.main.feels_like),
    humidity:  c.main.humidity,
    clouds:    c.clouds?.all ?? 0,
    windSpeed: c.wind?.speed ?? 0,
    windDeg:   c.wind?.deg ?? 0,
    windDir:   windDirLabel(c.wind?.deg),
    windGust:  c.wind?.gust ?? null,
    desc:      c.weather?.[0]?.description ?? '',
    icon:      c.weather?.[0]?.icon ?? '01d',
    city:      c.name ?? '',
  }
}

// Wind for the current view, best source first:
//   1. OWM box/city (paid plan): real stations, and the panel uses the nearest one.
//   2. Open-Meteo: a 5 × 4 grid over the view in one request, no key.
//   3. OWM single point at the centre: the whole view then blows one way (last resort).
async function fetchWindField() {
  const canvas = windCanvas.value
  const m = map()
  if (!canvas || !m) return
  const seq = ++windFetchSeq
  const size   = m.getSize()
  const extent = m.getView().calculateExtent(size)
  const pad    = (extent[2] - extent[0]) * 0.15
  const [minLon, minLat] = toLonLat([extent[0] - pad, extent[1] - pad])
  const [maxLon, maxLat] = toLonLat([extent[2] + pad, extent[3] + pad])
  const [cLon, cLat] = toLonLat(m.getView().getCenter())
  const zoom = Math.max(3, Math.min(14, Math.floor(m.getView().getZoom() ?? 7)))
  let points = null, source = null

  if (!boxCityDenied) {
    try {
      const d = await getWeatherBox(
        [minLon, minLat, maxLon, maxLat].map(v => v.toFixed(2)).join(','), zoom
      )
      if (d?.denied) boxCityDenied = true
      if (Array.isArray(d?.list) && d.list.length) {
        points = d.list
          .filter(c => c.wind?.speed > 0)
          .map(c => windPoint(c.coord.lat, c.coord.lon, c.wind.deg ?? 0, c.wind.speed))
        if (seq === windFetchSeq) {
          const nearest = d.list.reduce((a, c) =>
            (c.coord.lon - cLon) ** 2 + (c.coord.lat - cLat) ** 2 < (a.coord.lon - cLon) ** 2 + (a.coord.lat - cLat) ** 2 ? c : a)
          weatherInfo.value = weatherFromOwm(nearest)
        }
        source = 'owm-box'
      }
    } catch { /* fall through */ }
  }

  if (!points?.length) {
    try {
      const r = await fetch(openMeteoUrl(gridPoints(minLon, minLat, maxLon, maxLat, SAMPLE_COLS, SAMPLE_ROWS)))
      const parsed = r.ok ? parseOpenMeteo(await r.json()) : []
      if (parsed.length) {
        points = parsed
        source = 'open-meteo'
        // Temperature, clouds etc. still come from OWM at the centre; the wind shown is the
        // Open-Meteo sample nearest the centre, so the panel and the particles agree.
        await fetchWeather()
        const near = nearestPoint(parsed, cLon, cLat)
        if (seq === windFetchSeq && weatherInfo.value && near) {
          weatherInfo.value = { ...weatherInfo.value, windSpeed: near.speed, windDeg: near.deg,
                                windDir: windDirLabel(near.deg), windGust: near.gust }
        }
      }
    } catch { /* fall through */ }
  }

  if (!points?.length) {
    await fetchWeather()
    if (weatherInfo.value) {
      points = [windPoint(cLat, cLon, weatherInfo.value.windDeg ?? 0, weatherInfo.value.windSpeed)]
      source = 'owm-point'
    }
  }

  if (seq !== windFetchSeq || !points?.length) return   // a newer pan already asked again
  windField = points
  windSource.value = source
  buildWindGrid(canvas, m)
}

// Build an interpolated wind grid (IDW) so per-particle lookups are O(1), and place the
// measured points (arrows) in canvas pixels. Cheap: rebuilt whenever the view moves.
function buildWindGrid(canvas, m) {
  windGridDirty = false
  if (!windField.length) return
  const { width, height } = canvas
  windMarks = windField.length < 2 ? [] : windField.flatMap(pt => {
    const px = m.getPixelFromCoordinate(fromLonLat([pt.lon, pt.lat]))
    return px ? [{ x: px[0], y: px[1], ux: pt.vxNorm, uy: pt.vyNorm, speed: pt.speed }] : []
  })
  windGrid = Array.from({ length: GRID_ROWS }, (_, gy) =>
    Array.from({ length: GRID_COLS }, (_, gx) => {
      const px = (gx + 0.5) * width  / GRID_COLS
      const py = (gy + 0.5) * height / GRID_ROWS
      const coord = m.getCoordinateFromPixel([px, py])
      if (!coord) return { vx: 0, vy: 0 }
      const [lon, lat] = toLonLat(coord)
      let sx = 0, sy = 0, sw = 0
      for (const pt of windField) {
        const d2 = (pt.lon - lon) ** 2 + (pt.lat - lat) ** 2
        if (d2 < 1e-6) return { vx: pt.vxNorm * pt.speed * SPEED_SCALE, vy: pt.vyNorm * pt.speed * SPEED_SCALE }
        const w = 1 / d2
        sx += pt.vxNorm * pt.speed * w
        sy += pt.vyNorm * pt.speed * w
        sw += w
      }
      return sw > 0 ? { vx: sx / sw * SPEED_SCALE, vy: sy / sw * SPEED_SCALE } : { vx: 0, vy: 0 }
    })
  )
}

// One arrow per measured point, pointing downwind, with the speed (m/s) beside its tail (the side the
// wind comes from). Dark under light so it reads on every basemap.
function drawWindMarks(ctx) {
  ctx.save()
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  ctx.font = '600 11px system-ui'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  for (const k of windMarks) {
    const len = 22
    const tx = k.x - k.ux * len / 2, ty = k.y - k.uy * len / 2   // tail: upwind
    const hx = k.x + k.ux * len / 2, hy = k.y + k.uy * len / 2   // head: downwind
    const ax = -k.uy, ay = k.ux                                   // perpendicular
    const path = () => {
      ctx.beginPath()
      ctx.moveTo(tx, ty); ctx.lineTo(hx, hy)
      ctx.moveTo(hx - k.ux * 7 + ax * 5, hy - k.uy * 7 + ay * 5); ctx.lineTo(hx, hy)
      ctx.lineTo(hx - k.ux * 7 - ax * 5, hy - k.uy * 7 - ay * 5)
    }
    path(); ctx.strokeStyle = 'rgba(8,12,20,0.85)'; ctx.lineWidth = 5; ctx.stroke()
    path(); ctx.strokeStyle = '#f8fafc';           ctx.lineWidth = 2; ctx.stroke()
    const label = `${k.speed.toFixed(1)} m/s`
    // Centre the label beyond the tail, far enough along the arrow's line that its box clears it.
    const half = ctx.measureText(label).width / 2
    const gap = 6 + Math.abs(k.ux) * half + Math.abs(k.uy) * 7
    const lx = tx - k.ux * gap, ly = ty - k.uy * gap
    ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(8,12,20,0.85)'; ctx.strokeText(label, lx, ly)
    ctx.fillStyle = '#f8fafc'; ctx.fillText(label, lx, ly)
  }
  ctx.restore()
}

function getWindAt(px, py, w, h) {
  if (!windGrid) return { vx: 0, vy: 0 }
  const gx = Math.max(0, Math.min(GRID_COLS - 1, Math.floor(px / w * GRID_COLS)))
  const gy = Math.max(0, Math.min(GRID_ROWS - 1, Math.floor(py / h * GRID_ROWS)))
  return windGrid[gy][gx]
}

function mkParticle(w, h) {
  return { x: Math.random() * w, y: Math.random() * h,
           trail: [], age: Math.random() * 100, maxAge: 90 + Math.random() * 130 }
}

function startWindAnim() {
  const canvas = windCanvas.value
  if (!canvas) return
  const rect = canvas.parentElement.getBoundingClientRect()
  canvas.width  = rect.width - 260
  canvas.height = rect.height
  windLastTime  = null
  windParticles = Array.from({ length: PARTICLE_COUNT }, () => mkParticle(canvas.width, canvas.height))
  const view = map()?.getView()
  if (view) windViewKey = view.on(['change:center', 'change:resolution', 'change:rotation'], () => { windGridDirty = true })
  windAnimFrame = requestAnimationFrame(runWindAnim)
}

function stopWindAnim() {
  if (windAnimFrame) cancelAnimationFrame(windAnimFrame)
  windAnimFrame = null
  windParticles = []
  windLastTime  = null
  windField     = []
  windGrid      = null
  windMarks     = []
  windSource.value = null
  if (windViewKey) unByKey(windViewKey)
  windViewKey   = null
}

function runWindAnim(ts) {
  const canvas = windCanvas.value
  if (!canvas || weatherUi.layerId !== 'wind_new') { stopWindAnim(); return }
  const ctx = canvas.getContext('2d')
  const { width, height } = canvas
  if (!windLastTime) windLastTime = ts
  const dt = Math.min((ts - windLastTime) / 1000, 0.05)
  windLastTime = ts
  if (windGridDirty) { const m = map(); if (m) buildWindGrid(canvas, m) }
  ctx.clearRect(0, 0, width, height)
  for (const p of windParticles) {
    p.trail.push({ x: p.x, y: p.y })
    if (p.trail.length > TRAIL_LEN) p.trail.shift()
    const wind = getWindAt(p.x, p.y, width, height)
    p.x   += wind.vx * dt
    p.y   += wind.vy * dt
    p.age += dt * 60
    const oob = p.x < -20 || p.x > width + 20 || p.y < -20 || p.y > height + 20
    if (p.age > p.maxAge || oob) {
      Object.assign(p, mkParticle(width, height))
      continue
    }
    if (p.trail.length < 2) continue
    const grad = ctx.createLinearGradient(p.trail[0].x, p.trail[0].y, p.x, p.y)
    grad.addColorStop(0, 'rgba(180,220,255,0)')
    grad.addColorStop(1, 'rgba(210,238,255,0.75)')
    ctx.beginPath()
    ctx.moveTo(p.trail[0].x, p.trail[0].y)
    for (const pt of p.trail) ctx.lineTo(pt.x, pt.y)
    ctx.lineTo(p.x, p.y)
    ctx.strokeStyle = grad
    ctx.lineWidth   = 1.2
    ctx.lineCap     = 'round'
    ctx.stroke()
  }
  drawWindMarks(ctx)
  windAnimFrame = requestAnimationFrame(runWindAnim)
}

onUnmounted(() => {
  clearTimeout(weatherTimer)
  stopWindAnim()
  detachMap()
  // The overlay belongs to this view's map: the store must not keep a layer "on" for a fresh one.
  weatherUi.layerId = null
})
</script>

<style scoped>
.wind-canvas {
  position: absolute;
  top: 0; left: 0;
  width: calc(100% - 260px);
  height: 100%;
  pointer-events: none;
  z-index: 20;
}

.weather-panel {
  position: absolute;
  bottom: 70px;
  right: 272px;
  z-index: 50;
  background: rgba(10,12,18,0.9);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 8px;
  padding: 10px 14px;
  color: #fff;
  min-width: 190px;
  backdrop-filter: blur(4px);
}
.weather-header {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(255,255,255,0.08);
}
.weather-icon { width: 50px; height: 50px; flex-shrink: 0; }
.weather-temp { font-size: 20px; font-weight: 700; line-height: 1.2; }
.weather-feels { font-size: 11px; color: var(--text-muted); font-weight: 400; }
.weather-desc { font-size: 12px; color: var(--text-muted); text-transform: capitalize; }
.weather-rows { display: flex; flex-direction: column; gap: 4px; }
.weather-row { display: flex; justify-content: space-between; gap: 12px; font-size: 12px; }
.weather-label { color: var(--text-muted); }
.weather-wind { display: inline-flex; align-items: center; gap: 5px; }
.wind-arrow { display: inline-block; font-weight: 700; line-height: 1; }
.weather-city { color: var(--text-muted); font-size: 11px; margin-top: 4px; text-align: right; }
.weather-legend { margin-top: 10px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.08); }
.legend-bar { height: 8px; border-radius: 4px; width: 100%; }
.legend-stops { display: flex; justify-content: space-between; margin-top: 3px; font-size: 10px; color: var(--text-muted); }
</style>
