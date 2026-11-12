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

    <!-- Mode toggle (bottom-right of map, above tracker panel) -->
    <div class="mode-toggle">
      <button
        :class="['bm-btn', { active: viewMode === 'individuals' }]"
        @click="setViewMode('individuals')"
      >{{ t('map.modeIndividual') }}</button>
      <button
        :class="['bm-btn', { active: viewMode === 'groups' }]"
        @click="setViewMode('groups')"
      >{{ t('map.modeGroups') }}</button>
    </div>

    <!-- Tracker panel -->
    <aside ref="trackerPanelEl" class="tracker-panel">
      <div class="panel-header">
        <span>{{ t('map.trackers') }} ({{ displayList.length }})</span>
        <span v-if="store.hasSOS" class="badge badge-sos sos-pulse">SOS</span>
      </div>

      <!-- Devices we've stopped hearing from. Deliberately quiet: no pulse, no sound, no red —
           this is a "look at this" notice, not the SOS alarm. -->
      <div v-if="store.silentList.length" class="silence-notice">
        <span class="silence-dot" />
        <span class="silence-text">
          {{ t('map.silenceNotice', { n: store.silentList.length }) }}
          <template v-if="store.lostList.length">
            · {{ t('map.silenceLost', { n: store.lostList.length }) }}
          </template>
        </span>
      </div>
      <div class="rank-search">
        <input
          v-model="rankFilter"
          :placeholder="t('map.searchRank')"
          class="rank-input"
        />
        <button v-if="rankFilter" class="rank-clear" @click="rankFilter = ''">✕</button>
      </div>

      <!-- Individual mode -->
      <template v-if="viewMode === 'individuals'">
        <template v-for="pos in displayList" :key="pos.device_id">
        <div
          class="tracker-row"
          :class="[`fresh-${freshnessOf(pos, nowTick)}`, { 'tracker-sos': pos.sos_active, 'tracker-selected': selectedDeviceId === pos.device_id }]"
          :data-device-id="pos.device_id"
          tabindex="0"
          role="button"
          :aria-pressed="selectedDeviceId === pos.device_id"
          @click="selectDevice(pos)"
          @keydown.enter.self.prevent="selectDevice(pos)"
          @keydown.space.self.prevent="selectDevice(pos)"
        >
          <div class="tracker-dot" :style="{ background: pos.groups?.[0]?.color ?? '#3b82f6' }" />
          <div class="tracker-info">
            <div class="tracker-name">{{ pos.full_name || pos.device_name || pos.dev_sn }}</div>
            <div class="tracker-mgrs">
              {{ pos.mgrs }}
              <span v-if="pos.gnss_valid === false" class="no-fix-tag">{{ t('map.noFix') }}</span>
            </div>
          </div>
          <div class="tracker-meta">
            <div class="tracker-age" :class="`age-${freshnessOf(pos, nowTick)}`">
              {{ formatAge(ageMs(pos, nowTick)) }}
            </div>
            <div class="tracker-bat" :class="batClass(pos.battery_voltage)">
              {{ pos.battery_voltage?.toFixed(1) ?? '—' }}V
            </div>
          </div>
        </div>
        <div v-if="selectedDeviceId === pos.device_id" class="tracker-actions">
          <button type="button" class="tracker-report" data-testid="report-fire-row" @click="reportFromRow(pos)">
            {{ t('fire.report.atPosition') }}
          </button>
        </div>
        </template>
        <div v-if="!displayList.length" class="no-trackers">{{ t('map.noTrackers') }}</div>
      </template>

      <!-- Group mode -->
      <template v-else>
        <template v-for="group in groupsWithLeaders" :key="group.id">
          <div class="group-section-header" :style="{ borderLeftColor: group.color }">
            <span class="group-section-dot" :style="{ background: group.color }" />
            {{ group.name }}
          </div>
          <div v-if="group.leader" class="tracker-row tracker-leader"
               :class="{ 'tracker-selected': selectedDeviceId === group.leader.device_id }"
               :data-device-id="group.leader.device_id" tabindex="0" role="button"
               :aria-pressed="selectedDeviceId === group.leader.device_id"
               @click="selectDevice(group.leader)"
               @keydown.enter.self.prevent="selectDevice(group.leader)"
               @keydown.space.self.prevent="selectDevice(group.leader)">
            <div class="tracker-dot" :style="{ background: group.color }" />
            <div class="tracker-info">
              <div class="tracker-name">
                ★ {{ group.leader.full_name || group.leader.device_name || group.leader.dev_sn }}
              </div>
              <div class="tracker-mgrs">{{ group.leader.mgrs }}</div>
            </div>
            <div class="tracker-bat" :class="batClass(group.leader.battery_voltage)">
              {{ group.leader.battery_voltage?.toFixed(1) ?? '—' }}V
            </div>
          </div>
          <div v-if="group.leader && selectedDeviceId === group.leader.device_id" class="tracker-actions">
            <button type="button" class="tracker-report" data-testid="report-fire-row" @click="reportFromRow(group.leader)">
              {{ t('fire.report.atPosition') }}
            </button>
          </div>
          <div v-if="!group.leader" class="no-leader">{{ t('map.noLeader') }}</div>
        </template>
        <div v-if="!groupsWithLeaders.length" class="no-trackers">{{ t('map.noTrackers') }}</div>
      </template>
    </aside>
    <PanelHost :panels="mapPanels" :context="mapContext" />
  </div>
</template>

<script setup>
import { ref, shallowRef, computed, watch, onMounted, onUnmounted, onActivated, onDeactivated, nextTick } from 'vue'

defineOptions({ name: 'MapView' })
import { useI18n } from 'vue-i18n'
import { fromLonLat, toLonLat } from 'ol/proj'
import Overlay from 'ol/Overlay'
import { useLocationsStore } from '../stores/locations'
import { useFireStore } from '../stores/fire'
import { useFireUi } from '../modules/fire/index.js'
import { useAuthStore } from '../stores/auth'
import { useSettingsStore } from '../stores/settings'
import { useWebSocket } from '../composables/useWebSocket'
import { useMap, BASEMAPS } from '../composables/useMap'
import { getDevices, getGroupsWithMembers, setDeviceLocation } from '../api'
import { ageMs, contactAt, formatAge, freshnessOf, byUrgency } from '../lib/freshness'
import { unByKey } from 'ol/Observable'
import MapPopupHost from '../platform/map-shell/MapPopupHost.vue'
import MapContextMenu from '../platform/map-shell/MapContextMenu.vue'
import PanelHost from '../platform/PanelHost.vue'
import { collectContextMenu, collectLayerToggles, collectPanels, collectPopups } from '../platform/map-shell/contributions.js'
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
const viewMode       = ref('individuals') // 'individuals' | 'groups'
const rankFilter     = ref('')
// id -> { id, name, color, members: [{id, full_name, rank, is_leader}] }
const groupsMap      = ref({})

// Drives every relative age in the panel. Without it the ages would only refresh when some
// other device happens to report, so a panel full of silent trackers would freeze its own
// clock — exactly when the ages matter most.
const nowTick = ref(Date.now())
let tickTimer = null

const lastSyncLabel = computed(() => {
  if (!store.lastSyncAt) return '—'
  return new Date(store.lastSyncAt).toLocaleTimeString([], {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
})

const rankFiltered = computed(() => {
  const q = rankFilter.value.trim().toLowerCase()
  const list = !q
    ? store.positionList
    : store.positionList.filter(pos => pos.rank?.toLowerCase().includes(q))
  // Worst-first: SOS, then longest out of contact. What needs attention surfaces itself
  // rather than waiting to be scrolled to.
  return [...list].sort((a, b) => byUrgency(a, b, nowTick.value))
})

// In teams mode show only leaders, labelled by team name
const displayList = computed(() => {
  if (viewMode.value === 'individuals') return rankFiltered.value
  return rankFiltered.value
    .filter(pos => pos.groups?.some(g => g.is_leader))
    .map(pos => {
      const leaderGroup = pos.groups.find(g => g.is_leader)
      return { ...pos, displayLabel: leaderGroup?.name ?? pos.full_name }
    })
})

// Build a list of groups with their leader's live position for the panel
const groupsWithLeaders = computed(() => {
  const groupMap = {}
  for (const pos of rankFiltered.value) {
    for (const g of (pos.groups ?? [])) {
      if (!groupMap[g.id]) groupMap[g.id] = { id: g.id, name: g.name, color: g.color, leader: null }
      if (g.is_leader) groupMap[g.id].leader = pos
    }
  }
  return Object.values(groupMap).sort((a, b) => a.name.localeCompare(b.name))
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

// ── Volunteer selection and "Report fire at this position" ───────────────────────────────────
// Selecting a volunteer (panel row, or their marker on the map) reveals the action under their row.
const selectedDeviceId = ref(null)

function selectDevice(pos) {
  selectedDeviceId.value = pos.device_id
  focusDevice(pos)
}

// The position is frozen here, at the click: the volunteer keeps moving while the operator types,
// and what the form shows is exactly what is sent. No position, or none from the last 24 h
// (judged on received_at, the server clock), means nothing can be reported.
const REPORT_MAX_AGE_MS = 24 * 3_600_000
function reportFromRow(pos) {
  const live = store.positions[pos.device_id] ?? null
  const name = pos.full_name || pos.device_name || String(pos.dev_sn ?? '')
  const age = live ? ageMs(live) : null
  const lat = Number(live?.latitude), lon = Number(live?.longitude)
  const usable = !!live && live.latitude != null && live.longitude != null
    && Number.isFinite(lat) && Number.isFinite(lon) && age != null && age <= REPORT_MAX_AGE_MS
  useFireUi().openDialog({
    kind: 'report',
    target: usable
      ? { name, latitude: lat, longitude: lon, mgrs: live.mgrs ?? '', receivedAt: contactAt(live), gnssValid: live.gnss_valid }
      : { name, noPosition: true },
  })
}

// A marker click selects that volunteer's row and brings it into view; bare map deselects.
const trackerPanelEl = ref(null)
async function onMarkerClick(deviceId) {
  selectedDeviceId.value = deviceId
  if (!deviceId) return
  await nextTick()
  const row = [...(trackerPanelEl.value?.querySelectorAll('[data-device-id]') ?? [])].find(el => el.dataset.deviceId === deviceId)
  row?.scrollIntoView?.({ block: 'nearest' })
}
// A volunteer who left the list cannot stay selected.
watch(displayList, (list) => {
  if (selectedDeviceId.value && !list.some(p => p.device_id === selectedDeviceId.value)) selectedDeviceId.value = null
})

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

  tickTimer = setInterval(() => { nowTick.value = Date.now() }, 10_000)
})

// Redraw only when the point moves, not on every settings save.
watch(hqLocation, (v) => { if (!v) hqClearAsk.value = false })
watch(() => hqLocation.value && `${hqLocation.value.lat},${hqLocation.value.lon}`,
  () => setHQ(hqLocation.value), { immediate: true })

onUnmounted(() => {
  unmounted = true
  clearInterval(tickTimer)

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

function setViewMode(mode) {
  viewMode.value = mode
  refreshMarkers(displayList.value)
}

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
  closeContextMenu: () => ctxMenu.value?.close(),
}
const rootPanels = collectPanels(MODULES, 'map-root')
const toolbarPanels = collectPanels(MODULES, 'map-toolbar')
const mapPanels = collectPanels(MODULES, 'map')

function focusDevice(pos) {
  const m = map()
  if (m) m.getView().animate({ center: fromLonLat([pos.longitude, pos.latitude]), zoom: 13, duration: 500 })
}
function formatTime(ts) {
  if (!ts) return '—'
  return new Date(ts).toLocaleTimeString()
}
function batClass(v) {
  if (v == null) return ''
  if (v >= 3.5) return 'bat-ok'
  if (v >= 3.0) return 'bat-warn'
  return 'bat-low'
}
</script>

<style scoped>
.map-layout { flex: 1; display: flex; position: relative; overflow: hidden; }
.map-container { flex: 1; height: 100%; }


.basemap-switcher {
  position: absolute; bottom: 38px; left: 12px; z-index: 50;
  display: flex; gap: 4px; flex-wrap: wrap; max-width: 420px;
}
.mode-toggle {
  position: absolute; bottom: 38px; right: 12px; z-index: 50;
  display: flex; gap: 2px;
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

.tracker-panel {
  width: 260px; background: var(--bg-panel); border-left: 1px solid var(--border);
  overflow-y: auto; display: flex; flex-direction: column;
}
.panel-header {
  padding: 14px 16px; font-size: 13px; font-weight: 600;
  border-bottom: 1px solid var(--border); display: flex;
  align-items: center; justify-content: space-between; flex-shrink: 0;
}
.tracker-row {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 14px; cursor: pointer; border-bottom: 1px solid var(--border);
  transition: background .1s;
}
.tracker-row:hover { background: var(--bg-card); }
.tracker-sos    { border-left: 3px solid var(--danger); }
.tracker-leader { background: rgba(255,200,0,0.04); }
/* Freshness: the row dims as contact ages, so a silent tracker reads differently from a
   live one even before you look at the age figure. */
.tracker-row.fresh-stale .tracker-name,
.tracker-row.fresh-stale .tracker-mgrs { opacity: .72; }
.tracker-row.fresh-lost  .tracker-name,
.tracker-row.fresh-lost  .tracker-mgrs { opacity: .45; }
.tracker-row.fresh-stale { border-left: 3px solid rgba(234,179,8,.55); }
.tracker-row.fresh-lost  { border-left: 3px solid rgba(156,163,175,.5); }
.tracker-row.tracker-sos { border-left: 3px solid var(--danger); }

/* Selected volunteer: Signal Blue hairline (outline, not a side stripe) on the raised ground, and the
   report action underneath. */
.tracker-row:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.tracker-row.tracker-selected { background: var(--bg-card); outline: 1px solid var(--accent); outline-offset: -1px; }
.tracker-actions { padding: 8px 14px 10px; background: var(--bg-card); border-bottom: 1px solid var(--border); }
.tracker-report {
  width: 100%; min-height: 34px; padding: 6px 10px; font-size: 12.5px; font-weight: 600; line-height: 1.3;
  background: var(--bg-panel); color: var(--text); border: 1px solid var(--accent); border-radius: 6px;
}
.tracker-report:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
@media (hover: hover) and (pointer: fine) { .tracker-report:hover { background: var(--accent); color: #fff; opacity: 1; } }

.tracker-meta { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.tracker-age {
  font-size: 11px;
  font-family: monospace;
  font-variant-numeric: tabular-nums;
  color: var(--text-muted);
  min-width: 34px;
  text-align: right;
}
.age-stale { color: #eab308; font-weight: 600; }
.age-lost  { color: var(--danger); font-weight: 600; }

.no-fix-tag {
  font-family: system-ui;
  font-size: 9.5px;
  letter-spacing: .04em;
  text-transform: uppercase;
  color: #facc15;
  border: 1px solid rgba(250,204,21,.5);
  border-radius: 3px;
  padding: 0 3px;
  margin-left: 5px;
  vertical-align: 1px;
}

/* Quiet by design — this is not the SOS alarm and must not read like one. */
.silence-notice {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: rgba(234,179,8,.09);
  border-top: 1px solid rgba(234,179,8,.25);
  border-bottom: 1px solid rgba(234,179,8,.25);
  font-size: 12px;
  color: #eab308;
}
.silence-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: #eab308; flex-shrink: 0;
}
.silence-text { line-height: 1.35; }

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

.tracker-dot  { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.tracker-info { flex: 1; min-width: 0; }
.tracker-name { font-size: 13px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tracker-mgrs { font-size: 11px; color: var(--text-muted); font-family: monospace; }
.tracker-bat  { font-size: 11px; flex-shrink: 0; }
.bat-ok   { color: var(--success); }
.bat-warn { color: var(--warning); }
.bat-low  { color: var(--danger); }
.no-trackers { padding: 20px; text-align: center; color: var(--text-muted); font-size: 13px; }
.rank-search { padding: 8px 10px; border-bottom: 1px solid var(--border); display: flex; gap: 4px; flex-shrink: 0; }
.rank-input  { flex: 1; font-size: 12px; padding: 5px 8px; border-radius: 4px; border: 1px solid var(--border); background: var(--bg-card); color: var(--text); }
.rank-input::placeholder { color: var(--text-muted); }
.rank-clear  { background: none; border: none; color: var(--text-muted); font-size: 13px; padding: 0 4px; cursor: pointer; }
.rank-clear:hover { color: var(--text); }

.group-section-header {
  padding: 8px 14px 4px; font-size: 11px; font-weight: 700; text-transform: uppercase;
  letter-spacing: .05em; color: var(--text-muted); border-left: 3px solid transparent;
  display: flex; align-items: center; gap: 6px;
}
.group-section-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.no-leader { padding: 6px 14px 10px; font-size: 12px; color: var(--text-muted); font-style: italic; }

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
