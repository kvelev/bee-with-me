<template>
  <!-- Fire data freshness: always shows its age, and says so when it cannot. -->
  <div v-if="fireDataLayerOn" class="fire-pill" :class="`fire-${firePill.kind}`" role="status">
    <i18n-t v-if="firePill.time" keypath="fire.asOf" tag="span" class="fire-pill-main">
      <template #time><span class="fire-time">{{ firePill.time }}</span></template>
    </i18n-t>
    <span v-if="firePill.note" class="fire-pill-note">{{ firePill.note }}</span>
  </div>

  <!-- Licence attribution (text only: the offline build loads nothing from the network). -->
  <div v-if="fireDataLayerOn" class="fire-attribution">{{ t('fire.attribution') }}</div>

  <!-- "Show on map" from a fire alarm: a ring on the exact spot for a few seconds. -->
  <div ref="focusRingEl" class="fire-focus-anchor" aria-hidden="true">
    <div v-if="focusRingKey" :key="focusRingKey" class="fire-focus-ring" data-testid="fire-focus-ring" />
  </div>
</template>

<script setup>
// The fire module's part of the map: layer visibility, feed hand-over to the map, freshness pill,
// licence line and the focus ring. The map itself (OpenLayers) arrives through context.facade / context.mapKit.
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useFireStore } from '../store.js'
import { useFireUi } from '../ui.js'
import { firePillState } from '../lib/fireStyle.js'

const props = defineProps({ context: { type: Object, required: true } })

const { t, locale } = useI18n()
const fireStore = useFireStore()
const noop = () => { /* fetchFailed / zonesFailed drive the notices */ }

// ── Freshness pill ───────────────────────────────────────────────────────────
const nowTick = ref(Date.now())
const tickTimer = setInterval(() => { nowTick.value = Date.now() }, 10_000)

// The freshness pill and the licence line describe EFFIS data; zones are our own and need neither.
const fireDataLayerOn = computed(() => fireStore.layers.burnt || fireStore.layers.hotspots)

// What the pill says; the priority rules live in lib/fireStyle.js (firePillState).
const firePill = computed(() => {
  const at = fireStore.shownFetchedAt
  const time = at
    ? new Date(at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : ''
  const state = firePillState({
    at, upstreamState: fireStore.shownUpstreamState, failed: fireStore.fetchFailed, nowMs: nowTick.value,
  })
  return { kind: state.kind, time, note: state.noteKey ? t(state.noteKey) : '' }
})

// ── Feeds to the map ─────────────────────────────────────────────────────────
// immediate: a remounted map shows what the store already holds even if its own first refresh fails.
const facade = () => props.context.facade
watch(() => fireStore.hotspots,   (fc) => { if (!facade().setHotspots(fc))   fireStore.markFeedFailed('hotspots') }, { immediate: true })
watch(() => fireStore.burntAreas, (fc) => { if (!facade().setBurntAreas(fc)) fireStore.markFeedFailed('burnt') },    { immediate: true })
// Only active zones are drawn; Settings may have loaded disabled ones into the same list.
watch(() => fireStore.zones, (list) => facade().setZones(list.filter(z => z.is_active)), { immediate: true })

// ── Layer visibility ─────────────────────────────────────────────────────────
// Suppression zones are an admin tool. One synchronous watcher per layer: the map follows the flag in the same tick.
const layerOn = (name) => fireStore.layers[name] && (name !== 'zones' || !!props.context.isAdmin.value)
for (const name of ['burnt', 'hotspots', 'zones']) {
  watch(() => fireStore.layers[name], () => facade().setFireLayerVisible(name, layerOn(name)), { flush: 'sync' })
}

watch(locale, () => facade().setFireLabels({ fieldReport: t('fire.source.field_report') }))

// ── Focus ring ───────────────────────────────────────────────────────────────
const focusRingEl = ref(null)
const focusRingKey = ref(0)   // 0 = hidden; a new value restarts the pulse
const FOCUS_RING_MS = 8000
let focusOverlay = null
let focusMap = null
let focusRingTimer = null

function detachOverlay() {
  if (focusOverlay) focusMap?.removeOverlay(focusOverlay)
  focusOverlay = null
  focusMap = null
}

function attachOverlay(m) {
  detachOverlay()
  if (!m || !focusRingEl.value) return
  focusOverlay = new props.context.mapKit.Overlay({ element: focusRingEl.value, positioning: 'center-center', stopEvent: false })
  focusMap = m
  m.addOverlay(focusOverlay)
}

watch(() => props.context.hostMap.value, (m) => {
  attachOverlay(m)
  if (!m) { clearTimeout(focusRingTimer); focusRingKey.value = 0 }
}, { immediate: true, flush: 'sync' })

// "Show on map" from a fire alarm (FireAlarmBanner). The view is kept alive, so a request can
// land while it is hidden: it waits until the map is on screen, then centres once and is cleared.
function consumeFireFocus() {
  const req = fireStore.focusRequest
  const m = props.context.hostMap.value
  if (!req || !m || !props.context.mapActive.value) return
  fireStore.clearFocusRequest()
  // The fire is drawn on the hotspots layer, which is off by default: centring on it with the
  // layer off showed an empty map, as if the button did nothing.
  useFireUi().ensureLayer('hotspots')
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const center = props.context.mapKit.fromLonLat([req.longitude, req.latitude])
  m.updateSize()
  m.getView().animate({ center, zoom: 12, duration: reduce ? 0 : 500 })
  // Mark the spot itself, so it is found at once even before the hotspot data has drawn.
  focusOverlay?.setPosition(center)
  focusRingKey.value++
  clearTimeout(focusRingTimer)
  focusRingTimer = setTimeout(() => { focusRingKey.value = 0; focusOverlay?.setPosition(undefined) }, FOCUS_RING_MS)
}
watch(() => fireStore.focusRequest, consumeFireFocus)
watch(() => props.context.mapActive.value, (active) => { if (active) nextTick(consumeFireFocus) })

onMounted(() => {
  if (!focusOverlay) attachOverlay(props.context.hostMap.value)
  facade().setFireLabels({ fieldReport: t('fire.source.field_report') })
  // Layers remembered from the last session show again after a reload.
  for (const name of ['burnt', 'hotspots', 'zones']) facade().setFireLayerVisible(name, layerOn(name))
  fireStore.refreshVisible().catch(noop)
  if (props.context.isAdmin.value && fireStore.layers.zones) fireStore.fetchZones().catch(noop)
})

onUnmounted(() => {
  clearInterval(tickTimer)
  clearTimeout(focusRingTimer)
  detachOverlay()
})
</script>

<style scoped>
/* Fire data freshness. Neutral when live, muted when quiet or unknown, amber (never red)
   when stale or failed: red is reserved for alarms. */
.fire-pill {
  position: absolute; top: 48px; left: 12px; z-index: 50;
  display: flex; flex-direction: column; gap: 2px;
  max-width: 300px; padding: 5px 10px;
  background: var(--bg-panel); border: 1px solid var(--border);
  border-radius: 4px; font-size: 12px; color: var(--text);
}
.fire-pill-main { font-weight: 600; }
.fire-time { font-family: monospace; font-variant-numeric: tabular-nums; }
.fire-pill-note { font-size: 11px; color: var(--text-muted); line-height: 1.35; }
.fire-unknown .fire-pill-main, .fire-quiet .fire-pill-main { color: var(--text-muted); }
.fire-error {
  border-color: var(--warning-line);
  background: linear-gradient(var(--warning-wash), var(--warning-wash)), var(--bg-panel);
}
.fire-error .fire-pill-main, .fire-error .fire-pill-note { color: var(--warning); }

.fire-attribution {
  position: absolute; bottom: 8px; left: 12px; z-index: 50;
  max-width: max(calc(100% - 300px), 200px); padding: 2px 6px;
  background: rgba(15,17,23,.78); border-radius: 3px;
  font-size: 10.5px; line-height: 1.35; color: var(--text-muted);
  pointer-events: none;
}

/* "Show on map" ring: fire-alarm orange (the alarm the operator came from), dark halo for light
   basemaps. Pulses a few times, then holds until it is removed. */
.fire-focus-anchor { pointer-events: none; }
.fire-focus-ring {
  width: 56px; height: 56px; border-radius: 50%;
  border: 3px solid var(--fire-alarm);
  box-shadow: 0 0 0 2px rgba(0,0,0,.55), inset 0 0 0 2px rgba(0,0,0,.55);
  animation: fire-focus-pulse 1.2s ease-out 4;
}
@keyframes fire-focus-pulse {
  0%   { transform: scale(.5); opacity: 1; }
  70%  { transform: scale(1.15); opacity: .9; }
  100% { transform: scale(1); opacity: 1; }
}
@media (prefers-reduced-motion: reduce) {
  .fire-focus-ring { animation: none; }
}
</style>
