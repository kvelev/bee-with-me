<template>
  <PanelHost :panels="rootPanels" :context="mapContext" />
  <div class="map-layout">
    <div ref="mapEl" class="map-container" />

    <!-- The map never goes blank, but it must never claim to be live when it isn't. -->
    <div v-if="!store.wsConnected" class="stale-feed-banner">
      <span class="stale-feed-dot" />
      {{ t('map.feedLost', { time: lastSyncLabel }) }}
    </div>

    <!-- Cursor coordinate readout -->
    <div v-if="cursorCoords && (mgrsGridOn || latLonOn)" class="mgrs-readout">
      <span v-if="mgrsGridOn">{{ cursorCoords.mgrs }}</span>
      <span v-if="mgrsGridOn && latLonOn" class="readout-sep">|</span>
      <span v-if="latLonOn">{{ cursorCoords.lat.toFixed(5) }}, {{ cursorCoords.lon.toFixed(5) }}</span>
    </div>

    <!-- Basemap + grid + trail controls (bottom-left) -->
    <div class="basemap-switcher">
      <button
        v-for="bm in BASEMAPS" :key="bm.id"
        :class="['bm-btn', { active: activeBasemap === bm.id }]"
        @click="switchBasemap(bm.id)"
      >{{ t(`map.basemaps.${bm.id}`) }}</button>
      <button :class="['bm-btn', { active: mgrsGridOn }]" @click="toggleMGRS">
        {{ t('map.mgrsGrid') }}
      </button>
      <button :class="['bm-btn', { active: latLonOn }]" @click="toggleLatLon">
        {{ t('map.latLon') }}
      </button>
      <button :class="['bm-btn', { active: trailOn }]" @click="toggleTrail">
        {{ t('map.trail') }}
      </button>
      <button v-if="trailOn" :class="['bm-btn', { active: trailNumbersOn }]" @click="toggleTrailNumbers">
        {{ t('map.trailNumbers') }}
      </button>
      <button :class="['bm-btn', { active: measureOn }]" @click="toggleMeasure">
        {{ t('map.measure') }}
      </button>
      <button v-if="isAdmin" :class="['bm-btn', { active: hqMode }]" :disabled="!settingsReady" @click="toggleHQMode">
        {{ hqLocation ? t('map.hqMove') : t('map.hqSet') }}
      </button>
      <button v-if="isAdmin && hqLocation && !hqClearAsk" class="bm-btn bm-btn-danger" @click="hqClearAsk = true">
        {{ t('map.hqClear') }}
      </button>
      <span v-if="isAdmin && hqLocation && hqClearAsk" class="bm-hq-confirm" role="alertdialog">
        <span>{{ t('map.hqClearConfirm') }}</span>
        <button class="bm-btn bm-btn-danger" @click="clearHQ">{{ t('map.hqClearYes') }}</button>
        <button class="bm-btn" @click="hqClearAsk = false">{{ t('map.hqClearCancel') }}</button>
      </span>
      <span v-if="settingsFailed" class="bm-hq-note" role="status">
        {{ t('map.settingsUnavailable') }}
        <button class="bm-btn" @click="loadSettings">{{ t('map.settingsRetry') }}</button>
      </span>
      <span v-if="hqError" class="bm-hq-error" role="alert">{{ t('map.hqSaveFailed') }}</span>
      <span v-if="hqLayerFailed" class="bm-hq-error" role="alert">{{ t('map.hqLayerFailed') }}</span>
      <button v-if="isAdmin && repeaters.length" :class="['bm-btn', { active: repeaterMode }]" @click="toggleRepeaterMode">
        {{ t('map.repeaterSet') }}
      </button>
      <span v-if="isAdmin && repeaterMode" class="bm-hq-confirm">
        <select v-model="repeaterId" class="bm-select" :aria-label="t('map.repeaterPick')">
          <option v-for="r in repeaters" :key="r.id" :value="r.id">
            {{ r.name || `SN:${r.dev_sn}` }}{{ r.site_latitude != null ? ' ✓' : '' }}
          </option>
        </select>
        <span>{{ t('map.repeaterHint') }}</span>
        <button v-if="selectedRepeater?.site_latitude != null" class="bm-btn bm-btn-danger" @click="clearRepeater">
          {{ t('map.repeaterClear') }}
        </button>
      </span>
      <span v-if="repeaterError" class="bm-hq-error" role="alert">{{ t('map.repeaterSaveFailed') }}</span>
      <button
        v-for="{ toggle, name } in layerButtons" :key="toggle.id"
        :class="['bm-btn', { active: toggleOn(toggle, name) }]"
        :aria-pressed="toggleOn(toggle, name)"
        :data-layer="name"
        @click="onToggle(toggle, name)"
      >{{ t(toggle.labelKey) }}</button>
      <PanelHost :panels="toolbarPanels" :context="mapContext" />
    </div>

    <MapPopupHost :map="hostMap" :popups="popups" :selection="firePopup" anchor-class="fire-popup-anchor">
      <template #default="{ popup, selection }">
        <component :is="popup.component" :selection="selection" :context="mapContext" @close="firePopup = null" />
      </template>
    </MapPopupHost>

    <!-- Right-click / long-press on the map: the items come from the modules' contextMenu contributions. -->
    <MapContextMenu ref="ctxMenu" :items="menuItems" />

    <!-- Measure readout -->
    <div v-if="measureReadout" class="measure-readout">
      📏 {{ measureReadout.distKm.toFixed(2) }} km &nbsp;·&nbsp; {{ Math.round(measureReadout.bearing) }}°
    </div>

    <PanelHost :panels="mapPanels" :context="mapContext" />
  </div>
</template>

<script setup>
import { ref, shallowRef, computed, watch, onMounted, onUnmounted, onActivated, onDeactivated } from 'vue'
import { storeToRefs } from 'pinia'

defineOptions({ name: 'MapView' })
import { useI18n } from 'vue-i18n'
import { fromLonLat, toLonLat } from 'ol/proj'
import Overlay from 'ol/Overlay'
import { useLocationsStore } from '../stores/locations'
import { useFireStore } from '../stores/fire'
import { useFireUi } from '../modules/fire/index.js'
import { useTrackerUi } from '../modules/tracking/index.js'
import { useAuthStore } from '../stores/auth'
import { useSettingsStore } from '../stores/settings'
import { useWebSocket } from '../composables/useWebSocket'
import { useMap, BASEMAPS } from '../composables/useMap'
import { getDevices, getGroupsWithMembers, setDeviceLocation } from '../api'
import { unByKey } from 'ol/Observable'
import MapPopupHost from '../platform/map-shell/MapPopupHost.vue'
import MapContextMenu from '../platform/map-shell/MapContextMenu.vue'
import PanelHost from '../platform/PanelHost.vue'
import { collectActions, collectContextMenu, collectLayerToggles, collectPanels, collectPopups } from '../platform/map-shell/contributions.js'
import { MODULES } from '../modules'

const { t } = useI18n()
const store   = useLocationsStore()
const fireStore = useFireStore()
const authStore = useAuthStore()
const settingsStore = useSettingsStore()
const mapEl   = ref(null)

const activeBasemap  = ref('osm')
const mgrsGridOn     = ref(false)
const measureOn      = ref(false)
const measureReadout = ref(null)  // { distKm, bearing } | null
const trailOn        = ref(false)
const trailNumbersOn = ref(false)
const cursorCoords   = ref(null)   // { mgrs, lat, lon }
const latLonOn       = ref(false)
// The tracker list, its mode, filter and selection are the tracking module's (useTrackerUi). The view owns the tick
// and the reset, and hands the same displayList ref to the map that the tracker panel draws its rows from.
const trackerUi = useTrackerUi()
const { displayList, groupsMap, selectedDeviceId } = storeToRefs(trackerUi)

const lastSyncLabel = computed(() => {
  if (!store.lastSyncAt) return '—'
  return new Date(store.lastSyncAt).toLocaleTimeString([], {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
})

// HQ lives in the database (settings store); only an admin can place or clear it.
const isAdmin    = computed(() => authStore.user?.role === 'admin')
const hqLocation = computed(() => settingsStore.hq)
const hqMode     = ref(false)
const hqError    = ref(false)
const hqLayerFailed = ref(false)    // the HQ map layer is missing: placement mode could not start
const hqClearAsk = ref(false)       // the Clear HQ confirmation is showing
const settingsFailed = ref(false)   // settings could not be loaded: HQ is unknown, not absent
const settingsReady  = computed(() => !!settingsStore.settings)

async function loadSettings() {
  settingsFailed.value = false
  try {
    await settingsStore.fetchSettings()
  } catch {
    settingsFailed.value = true
    return
  }
  await settingsStore.migrateLocalHQ()   // handles role and failures itself
}

// Only the latest call may set or clear the error: a slow failure of an earlier click must not
// show "Could not save HQ" over a newer click that succeeded (the store already serialises the
// writes, so the latest call also finishes last).
let hqCall = 0
async function saveHQ(action) {
  const mine = ++hqCall
  hqError.value = false
  try {
    await action()
    if (mine === hqCall) hqError.value = false
  } catch {
    if (mine === hqCall) hqError.value = true
  }
}

const facade = useMap(
  mapEl,
  displayList,
  computed(() => store.trails),
  (coords) => { cursorCoords.value = coords },
  (data)   => { measureReadout.value = data },
  groupsMap,
  (coords) => {
    hqMode.value = false
    hqLayerFailed.value = false
    setHQPlacementMode(false)
    saveHQ(() => settingsStore.setHQ(coords.lat, coords.lon))
  },
  computed(() => settingsStore.photosOnMap),
)
const { map, setBasemap, setMGRSGrid, setLatLonGrid, setTrailVisible, setCheckpointNumbers, setMeasureMode, setWeatherLayer, refreshMarkers, setHQ, setHQPlacementMode, setRepeaters, setRepeaterPlacementMode, onRepeaterPlaced, onFireFeatureClick, onTrackerClick, onMapContextMenu } = facade
const { connect } = useWebSocket()

// ── Fire layers ──────────────────────────────────────────────────────────────
// Suppression zones are an admin tool: the button, the circles and the zone fetch are admin-only.
// The layer state, the pill and the focus ring belong to the fire module's map panel.
const layerToggles = computed(() => collectLayerToggles(MODULES).filter(t => !t.adminOnly || isAdmin.value))
// A toggle without the state pair (key + isOn + set) is a bare layer declaration: its name is the layer id
// without the `fire-` prefix and the fire stores drive it.
const layerButtons = computed(() => layerToggles.value
  .map(toggle => ({ toggle, name: toggle.key ?? toggle.id.replace(/^fire-/, '') })))
const firePopup   = ref(null)   // { kind, properties, coordinate } | null
// Popups come from the modules' contributions; the selected feature stays here, the popup owns its actions.
const popups = collectPopups(MODULES)
const hostMap = shallowRef(null)   // set once the map exists; the popup host puts its overlay on it

const toggleOn = (toggle, name) => (toggle.isOn ? !!toggle.isOn() : !!fireStore.layers[name])
const onToggle = (toggle, name) => (toggle.set ? toggle.set(!toggleOn(toggle, name)) : useFireUi().setLayer(name, !toggleOn(toggle, name)))

// A marker click selects that volunteer's row (the tracker panel brings it into view); bare map deselects.
// A volunteer who left the list cannot stay selected: the store clears that.
const onMarkerClick = (deviceId) => trackerUi.select(deviceId)

// ── Right-click / long-press: "Report fire here" ─────────────────────────────────────────────
// The menu items come from the modules' contributions ("Report fire here" is the fire module's).
const ctxMenu = ref(null)   // the MapContextMenu instance
const menuItems = collectContextMenu(MODULES)

function openContextMenu(e) {
  ctxMenu.value?.open({
    ...e,
    bounds: { width: mapEl.value?.clientWidth ?? 0, height: mapEl.value?.clientHeight ?? 0 },
  })
}

onMounted(() => {
  const m = map()
  if (!m) return
  hostMap.value = m
  onFireFeatureClick((sel) => { firePopup.value = sel })
})

onTrackerClick(onMarkerClick)
onMapContextMenu(openContextMenu)

// Repeaters have no GNSS: an admin places each one by hand, like HQ. Everyone sees the placed ones.
const repeaters     = ref([])
const repeaterMode  = ref(false)
const repeaterId    = ref(null)
const repeaterError = ref(false)
const selectedRepeater = computed(() => repeaters.value.find(r => r.id === repeaterId.value) || null)

async function loadRepeaters() {
  try {
    repeaters.value = (await getDevices()).filter(d => d.device_type === 'repeater')
  } catch { /* the map does not depend on repeaters; keep what is drawn */ }
}
watch(repeaters, (list) => setRepeaters(list), { immediate: true })

async function saveRepeater(id, lat, lon) {
  repeaterError.value = false
  try {
    const row = await setDeviceLocation(id, lat, lon)
    repeaters.value = repeaters.value.map(r => (r.id === id ? { ...r, ...row } : r))
  } catch {
    repeaterError.value = true
  }
}
onRepeaterPlaced(({ lat, lon }) => {
  if (!repeaterId.value) return
  repeaterMode.value = false
  setRepeaterPlacementMode(false)
  saveRepeater(repeaterId.value, lat, lon)
})
function clearRepeater() {
  if (!repeaterId.value) return
  repeaterMode.value = false
  setRepeaterPlacementMode(false)
  saveRepeater(repeaterId.value, null, null)
}
function toggleRepeaterMode() {
  repeaterMode.value = !repeaterMode.value
  if (repeaterMode.value) {
    // Default to the first repeater not yet placed, so placing a fresh batch is click, click, click.
    if (!selectedRepeater.value) repeaterId.value = (repeaters.value.find(r => r.site_latitude == null) || repeaters.value[0])?.id ?? null
    if (measureOn.value) { measureOn.value = false; setMeasureMode(false) }
    if (hqMode.value) { hqMode.value = false; setHQPlacementMode(false) }
  }
  setRepeaterPlacementMode(repeaterMode.value)
}
// Set on unmount so a mount that is still awaiting (backend slow or down) does not go on to open a
// socket, register listeners or start the tick on a view that is already gone.
let unmounted = false

function reloadOfflineBasemap() {
  if (activeBasemap.value === 'offline') {
    setBasemap('offline')
  }
}



onMounted(async () => {
  trackerUi.reset()   // the mode, the filter and the selection start fresh on every visit
  // The browser can open before uvicorn is up (start.ps1). A failed first snapshot must not stop the
  // rest of mount: without connect() there is no socket, no resync timer and no reconnect, so SOS
  // pushes and live positions would never arrive until a reload (BP-02).
  const snapshot = await Promise.allSettled([store.fetchLive(), store.fetchSOS(), store.fetchTrail()])
  if (unmounted) return
  // catchUp: the first socket open pulls the snapshot and fire layers that this attempt missed.
  connect({ catchUp: snapshot.some(r => r.status === 'rejected') })
  // Build group member cache for hover tooltips (single request instead of N+1). Only the tooltips
  // depend on it, so a failure must not abort the mount.
  try {
    const { items: groups } = await getGroupsWithMembers({ limit: 500 })
    groupsMap.value = Object.fromEntries(groups.map(g => [g.id, g]))
  } catch { /* backend not up yet: tooltips show no group list */ }
  if (unmounted) return

  window.addEventListener('offline-map-changed', reloadOfflineBasemap)
  
  // HQ comes from the database. A failure shows an amber note with a retry; the map and live
  // data do not depend on it.
  await loadSettings()
  if (unmounted) return
  await loadRepeaters()
  if (unmounted) return

  trackerUi.startTick()   // idempotent; the order of the list and the marker styles follow it
})

// Redraw only when the point moves, not on every settings save.
watch(hqLocation, (v) => { if (!v) hqClearAsk.value = false })
watch(() => hqLocation.value && `${hqLocation.value.lat},${hqLocation.value.lon}`,
  () => setHQ(hqLocation.value), { immediate: true })

onUnmounted(() => {
  unmounted = true
  trackerUi.stopTick()

  window.removeEventListener('offline-map-changed', reloadOfflineBasemap)

  // The popup overlay belongs to this view; do not leave it on a map that outlives it.
  onFireFeatureClick(null)
  onTrackerClick(null)
  onMapContextMenu(null)
  onRepeaterPlaced(null)
  ctxMenu.value?.close()
  hostMap.value = null
})

function switchBasemap(id) {
  activeBasemap.value = id
  setBasemap(id)
}
watch(displayList, (list) => refreshMarkers(list), { deep: true })

function toggleMGRS() {
  mgrsGridOn.value = !mgrsGridOn.value
  setMGRSGrid(mgrsGridOn.value)
}
function toggleLatLon() {
  latLonOn.value = !latLonOn.value
  setLatLonGrid(latLonOn.value)
}
function toggleTrail() {
  trailOn.value = !trailOn.value
  setTrailVisible(trailOn.value)
}
function toggleTrailNumbers() {
  trailNumbersOn.value = !trailNumbersOn.value
  setCheckpointNumbers(trailNumbersOn.value)
}
function toggleMeasure() {
  measureOn.value = !measureOn.value
  if (measureOn.value && hqMode.value) {
    hqMode.value = false
    setHQPlacementMode(false)
  }
  if (measureOn.value && repeaterMode.value) {
    repeaterMode.value = false
    setRepeaterPlacementMode(false)
  }
  setMeasureMode(measureOn.value)
}
function toggleHQMode() {
  hqLayerFailed.value = false
  if (hqMode.value) {
    hqMode.value = false
    setHQPlacementMode(false)
    return
  }
  // The HQ map entry may be missing: only a strict `false` means it could not switch on.
  // Then nothing else is touched, so measure/repeater modes stay as they were.
  if (setHQPlacementMode(true) === false) {
    hqLayerFailed.value = true
    return
  }
  hqMode.value = true
  if (measureOn.value) {
    measureOn.value = false
    setMeasureMode(false)
  }
  if (repeaterMode.value) {
    repeaterMode.value = false
    setRepeaterPlacementMode(false)
  }
  // Switching the others off resets the map cursor, so re-assert HQ last (idempotent)
  // to keep the crosshair while HQ placement is on.
  setHQPlacementMode(true)
}
function clearHQ() {
  hqClearAsk.value = false
  saveHQ(() => settingsStore.clearHQ())
  if (hqMode.value) {
    hqMode.value = false
    setHQPlacementMode(false)
  }
}
// The view is kept alive; the fire map panel waits for mapActive before it handles a "Show on map" request.
const mapActive = ref(false)
onActivated(() => { mapActive.value = true; loadRepeaters() })
onDeactivated(() => { mapActive.value = false })

// What a module panel may use of the map shell: the refs themselves, not their values.
const mapKit = { Overlay, fromLonLat, toLonLat, unByKey }
const mapContext = {
  hostMap, facade, mapKit, isAdmin, activeBasemap, mapActive, selectedDeviceId,
  hasSOS: computed(() => store.hasSOS),
  rowActions: collectActions(MODULES, 'tracker-row'),
  closeContextMenu: () => ctxMenu.value?.close(),
}
const rootPanels = collectPanels(MODULES, 'map-root')
const toolbarPanels = collectPanels(MODULES, 'map-toolbar')
const mapPanels = collectPanels(MODULES, 'map')
</script>

<style scoped>
.map-layout { flex: 1; display: flex; position: relative; overflow: hidden; }
.map-container { flex: 1; height: 100%; }


.basemap-switcher {
  position: absolute; bottom: 38px; left: 12px; z-index: 50;
  display: flex; gap: 4px; flex-wrap: wrap; max-width: 420px;
}
.bm-btn {
  background: var(--bg-panel); border: 1px solid var(--border);
  color: var(--text-muted); padding: 5px 10px; font-size: 12px; border-radius: 4px;
}
.bm-btn:hover  { color: var(--text); }
.bm-btn.active { background: var(--accent); border-color: var(--accent); color: #fff; }
.bm-btn-danger { color: #f87171; border-color: rgba(248,113,113,0.35); }
.bm-btn-danger:hover { background: rgba(248,113,113,0.1); color: #fca5a5; }
.bm-hq-error { font-size: 12px; color: var(--warning); align-self: center; }
.bm-hq-confirm, .bm-hq-note { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; align-self: center; }
.bm-hq-confirm { color: var(--text); }
.bm-hq-note { color: var(--warning); }
.bm-btn:disabled { opacity: .45; cursor: not-allowed; }
.bm-select { background: var(--bg-panel); border: 1px solid var(--border); color: var(--text); padding: 4px 6px; font-size: 12px; border-radius: 4px; width: auto; }

/* Not positioned: OpenLayers sizes its overlay container from this element. */
.fire-popup-anchor { display: block; }

.stale-feed-banner {
  position: absolute;
  top: 12px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 60;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 7px 15px;
  border-radius: 20px;
  background: rgba(120,53,15,.94);
  border: 1px solid rgba(234,179,8,.5);
  color: #fde68a;
  font-size: 12.5px;
  font-weight: 600;
  box-shadow: 0 3px 14px rgba(0,0,0,.4);
}
.stale-feed-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: #eab308; flex-shrink: 0;
  animation: feed-blink 1.6s ease-in-out infinite;
}
@keyframes feed-blink { 0%,100% { opacity: 1; } 50% { opacity: .25; } }
@media (prefers-reduced-motion: reduce) {
  .stale-feed-dot { animation: none; }
}

.measure-readout {
  position: absolute; top: 56px; left: 50%; transform: translateX(-50%);
  background: rgba(15,30,100,0.92); color: #93c5fd;
  font-family: monospace; font-size: 13px; font-weight: 600;
  padding: 5px 14px; border-radius: 6px; pointer-events: none;
  border: 1px solid rgba(99,155,255,0.6); z-index: 50;
  letter-spacing: .04em;
  backdrop-filter: blur(4px);
}

.mgrs-readout {
  position: absolute; top: 12px; left: 50%; transform: translateX(-50%);
  background: rgba(15,15,20,0.82); color: #fff;
  font-family: monospace; font-size: 13px; font-weight: 600;
  padding: 5px 14px; border-radius: 6px; pointer-events: none;
  border: 1px solid rgba(255,255,255,0.12); z-index: 50;
  letter-spacing: .04em;
}

:deep(.ol-attribution) { display: none; }

:deep(.ol-scale-line) {
  background: rgba(15,15,20,0.75);
  border-radius: 4px;
  padding: 4px 8px;
  bottom: auto;
  top: 12px;
  left: 12px;
}
:deep(.ol-scale-line-inner) {
  color: #fff;
  border-color: #fff;
  font-size: 11px;
  font-family: monospace;
}
</style>
