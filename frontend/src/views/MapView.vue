<template>
  <SOSToast />
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

    <!-- Serial device status (bottom-left, above basemap controls) -->
    <div v-if="store.serialStatus" class="serial-status" :class="store.serialStatus.connected ? 'serial-ok' : 'serial-off'">
      <span class="serial-dot" />
      <span v-if="store.serialStatus.connected">
        {{ t('map.serialConnected') }} · {{ store.serialStatus.port }} · {{ store.serialStatus.frames_received }} frames
      </span>
      <span v-else>{{ t('map.serialDisconnected') }} · {{ store.serialStatus.port }}</span>
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
      <button
        v-for="name in fireLayerButtons" :key="name"
        :class="['bm-btn', { active: fireStore.layers[name] }]"
        :aria-pressed="fireStore.layers[name]"
        :data-layer="name"
        @click="toggleFire(name)"
      >{{ t(`fire.layers.${name}`) }}</button>
      <span v-if="isAdmin && fireStore.layers.zones && fireStore.zonesFailed" class="bm-hq-note" role="status">
        {{ t('fire.zone.loadFailed') }}
        <button class="bm-btn" @click="retryZones">{{ t('fire.zone.retry') }}</button>
      </span>
      <template v-if="activeBasemap === 'satellite'">
        <span class="bm-row-break" />
        <button
          v-for="wl in WEATHER_LAYERS" :key="wl.id"
          :class="['bm-btn', 'bm-btn-weather', { active: weatherLayerId === wl.id }]"
          @click="toggleWeather(wl.id)"
        >{{ t(`map.weather.${wl.id}`) }}</button>
      </template>
    </div>

    <!-- Fire data freshness: always shows its age, and says so when it cannot. -->
    <div v-if="fireDataLayerOn" class="fire-pill" :class="`fire-${firePill.kind}`" role="status">
      <i18n-t v-if="firePill.time" keypath="fire.asOf" tag="span" class="fire-pill-main">
        <template #time><span class="fire-time">{{ firePill.time }}</span></template>
      </i18n-t>
      <span v-if="firePill.note" class="fire-pill-note">{{ firePill.note }}</span>
    </div>

    <!-- Licence attribution (text only: the offline build loads nothing from the network). -->
    <div v-if="fireDataLayerOn" class="fire-attribution">{{ t('fire.attribution') }}</div>

    <!-- OpenLayers moves this element into its overlay; the popup inside is a Vue component. -->
    <!-- "Show on map" from a fire alarm: a ring on the exact spot for a few seconds. -->
    <div ref="focusRingEl" class="fire-focus-anchor" aria-hidden="true">
      <div v-if="focusRingKey" :key="focusRingKey" class="fire-focus-ring" data-testid="fire-focus-ring" />
    </div>
    <div ref="firePopupEl" class="fire-popup-anchor">
      <FirePopup
        v-if="firePopup"
        :kind="firePopup.kind"
        :properties="firePopup.properties"
        :lon-lat="firePopupLonLat"
        :is-admin="isAdmin"
        :busy="fireBusy"
        :error-text="fireError"
        @close="closeFirePopup"
        @dismiss="onPopupDismiss"
        @extinguish="onPopupExtinguish"
        @create-zone="onPopupCreateZone"
      />
    </div>

    <!-- Right-click / long-press on the map: the only item is "Report fire here". -->
    <div v-if="ctxMenu" ref="ctxMenuEl" class="map-context" role="menu" :style="{ left: ctxMenu.x + 'px', top: ctxMenu.y + 'px' }">
      <button type="button" role="menuitem" class="mc-item" data-testid="report-fire-here" @click="reportFromMenu">
        {{ t('fire.report.here') }}
      </button>
    </div>

    <FieldReportForm
      v-if="dialog?.kind === 'report'"
      :target="dialog.target"
      :busy="dialogBusy"
      :error-text="dialogError"
      @submit="submitReport"
      @cancel="closeDialog"
    />
    <SuppressionZoneForm
      v-if="dialog?.kind === 'zone'"
      :latitude="dialog.latitude"
      :longitude="dialog.longitude"
      :busy="dialogBusy"
      :error-text="dialogError"
      @submit="submitZone"
      @cancel="closeDialog"
    />

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

    <!-- Wind particle canvas -->
    <canvas v-if="weatherLayerId === 'wind_new'" ref="windCanvas" class="wind-canvas" />

    <!-- Weather info panel -->
    <div v-if="weatherLayerId && weatherInfo" class="weather-panel">
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
        <div v-if="weatherLayerId === 'wind_new' && windSourceLabel" class="weather-row weather-city">{{ t('map.weatherWindSource', { source: windSourceLabel }) }}</div>
      </div>
      <div v-if="activeWeatherLayer" class="weather-legend">
        <div class="legend-bar" :style="{ background: activeWeatherLayer.gradient }" />
        <div class="legend-stops">
          <span v-for="s in activeWeatherLayer.stops" :key="s">{{ s }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, onActivated, onDeactivated, nextTick } from 'vue'

defineOptions({ name: 'MapView' })
import { useI18n } from 'vue-i18n'
import { fromLonLat, toLonLat } from 'ol/proj'
import Overlay from 'ol/Overlay'
import { useLocationsStore } from '../stores/locations'
import { useFireStore } from '../stores/fire'
import { useAuthStore } from '../stores/auth'
import { useSettingsStore } from '../stores/settings'
import { useWebSocket } from '../composables/useWebSocket'
import { useMap, BASEMAPS } from '../composables/useMap'
import { getGroupsWithMembers, getSerialStatus } from '../api'
import { ageMs, contactAt, formatAge, freshnessOf, byUrgency } from '../lib/freshness'
import { firePillState } from '../lib/fireStyle'
import { recolorFor, tempLegendGradient } from '../lib/weatherTiles'
import { compassFrom, windPoint, gridPoints, openMeteoUrl, parseOpenMeteo, nearestPoint } from '../lib/wind'
import { unByKey } from 'ol/Observable'
import SOSToast from '../components/SOSToast.vue'
import FirePopup from '../components/FirePopup.vue'
import FieldReportForm from '../components/FieldReportForm.vue'
import SuppressionZoneForm from '../components/SuppressionZoneForm.vue'
import { fireErrorKey } from '../lib/fireErrors'

const OWM_KEY = import.meta.env.VITE_OWM_API_KEY ?? ''
const WEATHER_LAYERS = [
  {
    // Clouds and rain are recoloured from OWM's faint tiles (lib/weatherTiles.js); these legends
    // show that output: white rising with cover from 10 %, and the 0.1 / 1 / 5 / 20 mm/h rain scale.
    id: 'clouds_new',
    gradient: 'linear-gradient(to right, rgba(244,247,252,0) 0%, rgba(244,247,252,0.2) 20%, rgba(244,247,252,0.5) 60%, rgba(244,247,252,0.8) 100%)',
    stops: ['10%', '50%', '100%'],
  },
  {
    id: 'precipitation_new',
    gradient: 'linear-gradient(to right, rgba(160,216,239,0.55), rgba(65,105,225,0.75), rgba(0,0,205,0.85), rgba(102,0,204,0.9))',
    stops: ['0.1', '1', '5', '20 mm/h'],
  },
  {
    id: 'wind_new',
    gradient: 'linear-gradient(to right, #2c45e8, #54b5e6, #7bcb6b, #e8e04a, #e87b3b, #e83b2c)',
    stops: ['0', '5', '15', '30 m/s'],
  },
  {
    // Recoloured into 2 °C bands with contours (lib/weatherTiles.js); OWM's data stops at 30 °C.
    id: 'temp_new',
    gradient: tempLegendGradient(),
    stops: ['-20°', '5°', '30°C+'],   // evenly spaced labels on a linear −20 … 30 °C bar
  },
]

const { t, locale } = useI18n()
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
const weatherLayerId  = ref(null)
const weatherInfo     = ref(null)
let   weatherTimer    = null
const activeWeatherLayer = computed(() => WEATHER_LAYERS.find(l => l.id === weatherLayerId.value) ?? null)
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

const { map, setBasemap, setMGRSGrid, setLatLonGrid, setTrailVisible, setCheckpointNumbers, setMeasureMode, setWeatherLayer, refreshMarkers, setHQ, setHQPlacementMode, setBurntAreas, setHotspots, setFireLayerVisible, setFireLabels, onFireFeatureClick, setZones, onTrackerClick, onMapContextMenu } = useMap(
  mapEl,
  displayList,
  computed(() => store.trails),
  (coords) => { cursorCoords.value = coords },
  (data)   => { measureReadout.value = data },
  groupsMap,
  (coords) => {
    hqMode.value = false
    setHQPlacementMode(false)
    saveHQ(() => settingsStore.setHQ(coords.lat, coords.lon))
  },
  computed(() => settingsStore.photosOnMap),
)
const { connect } = useWebSocket()

// ── Fire layers ──────────────────────────────────────────────────────────────
const FIRE_LAYER_BUTTONS = ['burnt', 'hotspots', 'zones']
// Suppression zones are an admin tool: the button, the circles and the zone fetch are admin-only.
const fireLayerButtons = computed(() => FIRE_LAYER_BUTTONS.filter(n => n !== 'zones' || isAdmin.value))
// The freshness pill and the licence line describe EFFIS data; zones are our own and need neither.
const fireDataLayerOn = computed(() => fireStore.layers.burnt || fireStore.layers.hotspots)
const firePopupEl = ref(null)
const focusRingEl = ref(null)
const focusRingKey = ref(0)   // 0 = hidden; a new value restarts the pulse
const FOCUS_RING_MS = 8000
let focusOverlay = null
let focusRingTimer = null
const firePopup   = ref(null)   // { kind, properties, coordinate } | null
let   fireOverlay = null
let   fireMap = null

function toggleFire(name) {
  const on = !fireStore.layers[name]
  setFireLayerVisible(name, on)
  if (!on && firePopup.value && name !== 'zones' && (name === 'hotspots') === (firePopup.value.kind === 'hotspot')) closeFirePopup()
  fireStore.setLayer(name, on).catch(() => { /* fetchFailed / zonesFailed drive the notices */ })
}

// A new report or zone must be visible where it was just made: switch its layer on if it is off.
function ensureLayer(name) { if (!fireStore.layers[name]) toggleFire(name) }

function retryZones() { fireStore.fetchZones().catch(() => { /* zonesFailed shows the note */ }) }

// The overlay coordinate is in the map projection (EPSG:3857); the popup wants WGS84.
const firePopupLonLat = computed(() => {
  const c = firePopup.value?.coordinate
  return Array.isArray(c) ? toLonLat(c) : null
})

function closeFirePopup() {
  firePopup.value = null
  fireError.value = ''
  fireOverlay?.setPosition(undefined)
}

// ── Popup actions (admin: dismiss, create zone; anyone: extinguish a field report) ──────────
const fireBusy  = ref(false)
const fireError = ref('')

// Only one popup action runs at a time. The server answers with the changed row; the popup then
// shows that row (state chip, notes) instead of the copy it was opened with.
async function runPopupAction(id, action) {
  if (fireBusy.value) return
  fireBusy.value = true
  fireError.value = ''
  try {
    await action()
    syncPopup(id)
  } catch (err) {
    if (firePopup.value?.properties?.id === id) fireError.value = t(fireErrorKey(err))
  } finally {
    fireBusy.value = false
  }
}

function syncPopup(id) {
  if (firePopup.value?.properties?.id !== id) return
  const next = fireStore.hotspots.features.find(f => f.id === id)
  if (next) firePopup.value = { ...firePopup.value, properties: { ...next.properties } }
}

const onPopupDismiss    = ({ id, notes }) => runPopupAction(id, () => fireStore.dismissHotspot(id, notes))
const onPopupExtinguish = ({ id }) => runPopupAction(id, () => fireStore.extinguish(id))
function onPopupCreateZone() {
  const ll = firePopupLonLat.value
  if (!ll) return
  openDialog({ kind: 'zone', latitude: ll[1], longitude: ll[0] })
  closeFirePopup()
}

// ── Dialogs: field report, suppression zone (one at a time) ──────────────────────────────────
const dialog      = ref(null)   // { kind: 'report', target } | { kind: 'zone', latitude, longitude } | null
const dialogBusy  = ref(false)
const dialogError = ref('')
let   dialogSeq   = 0

function openDialog(next) {
  closeContextMenu()
  dialogSeq++
  dialogBusy.value = false
  dialogError.value = ''
  dialog.value = next
}
function closeDialog() {
  dialogSeq++
  dialog.value = null
  dialogBusy.value = false
  dialogError.value = ''
}

// Runs a write for the open dialog. A dialog that was closed or replaced while the request was
// in flight takes neither the result nor the error.
async function runDialogAction(action, context) {
  if (dialogBusy.value) return false
  const mine = ++dialogSeq
  dialogBusy.value = true
  dialogError.value = ''
  try {
    await action()
    if (mine === dialogSeq) closeDialog()
    return true
  } catch (err) {
    if (mine === dialogSeq) { dialogError.value = t(fireErrorKey(err, context)); dialogBusy.value = false }
  }
  return false
}

async function submitReport({ notes }) {
  const target = dialog.value?.target
  if (!target) return
  if (target.noPosition) return
  const body = { latitude: target.latitude, longitude: target.longitude, notes }
  // A 404 here means the running backend lacks the field-report endpoint (older than T18).
  if (await runDialogAction(() => fireStore.reportFire(body), 'report')) ensureLayer('hotspots')
}

async function submitZone(values) {
  const d = dialog.value
  if (d?.kind !== 'zone') return
  const body = { ...values, latitude: d.latitude, longitude: d.longitude }
  if (await runDialogAction(() => fireStore.createZone(body))) ensureLayer('zones')
}

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
  openDialog({
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
const ctxMenu   = ref(null)   // { x, y, coordinate } | null
const ctxMenuEl = ref(null)

function closeContextMenu() {
  if (!ctxMenu.value) return
  ctxMenu.value = null
  document.removeEventListener('pointerdown', onOutsidePointer, true)
  document.removeEventListener('keydown', onMenuKey, true)
}
function onOutsidePointer(e) { if (!ctxMenuEl.value?.contains(e.target)) closeContextMenu() }
function onMenuKey(e) { if (e.key === 'Escape') closeContextMenu() }

async function openContextMenu({ coordinate, pixel }) {
  const width = mapEl.value?.clientWidth ?? 0
  const height = mapEl.value?.clientHeight ?? 0
  // Keep the menu inside the map (about 190 x 44 px).
  const x = Math.max(4, Math.min(pixel[0], width ? width - 196 : pixel[0]))
  const y = Math.max(4, Math.min(pixel[1], height ? height - 52 : pixel[1]))
  const first = !ctxMenu.value
  ctxMenu.value = { x, y, coordinate }
  if (first) {
    document.addEventListener('pointerdown', onOutsidePointer, true)
    document.addEventListener('keydown', onMenuKey, true)
  }
  await nextTick()
  ctxMenuEl.value?.querySelector('button')?.focus()
}

function reportFromMenu() {
  const c = ctxMenu.value?.coordinate
  if (!c) return
  const [lon, lat] = toLonLat(c)
  openDialog({ kind: 'report', target: { latitude: lat, longitude: lon } })
}

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

onMounted(() => {
  const m = map()
  if (!m) return
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  fireOverlay = new Overlay({
    element: firePopupEl.value,
    positioning: 'bottom-center',
    offset: [0, -16],
    stopEvent: true,
    autoPan: { animation: { duration: reduce ? 0 : 200 }, margin: 24 },
  })
  fireMap = m
  m.addOverlay(fireOverlay)
  focusOverlay = new Overlay({ element: focusRingEl.value, positioning: 'center-center', stopEvent: false })
  m.addOverlay(focusOverlay)
  onFireFeatureClick(async (sel) => {
    fireError.value = ''
    firePopup.value = sel
    // The popup has no size until Vue renders it; position after that so OpenLayers
    // anchors it by its real width and height.
    await nextTick()
    fireOverlay.setPosition(sel ? sel.coordinate : undefined)
  })
  setFireLabels({ fieldReport: t('fire.source.field_report') })
  // Layers remembered from the last session show again after a reload.
  for (const name of FIRE_LAYER_BUTTONS) setFireLayerVisible(name, fireStore.layers[name] && (name !== 'zones' || isAdmin.value))
  fireStore.refreshVisible().catch(() => { /* fetchFailed drives the pill */ })
  if (isAdmin.value && fireStore.layers.zones) retryZones()
})

// immediate: a remounted MapView shows what the store already holds even if its own first
// refresh fails.
watch(() => fireStore.hotspots,   (fc) => { if (!setHotspots(fc))   fireStore.markFeedFailed('hotspots') }, { immediate: true })
watch(() => fireStore.burntAreas, (fc) => { if (!setBurntAreas(fc)) fireStore.markFeedFailed('burnt') },    { immediate: true })
watch(locale, () => setFireLabels({ fieldReport: t('fire.source.field_report') }))
// Only active zones are drawn; Settings may have loaded disabled ones into the same list.
watch(() => fireStore.zones, (list) => setZones(list.filter(z => z.is_active)), { immediate: true })

onTrackerClick(onMarkerClick)
onMapContextMenu(openContextMenu)

onMounted(async () => {
  await Promise.all([store.fetchLive(), store.fetchSOS(), store.fetchTrail()])
  connect()
  // Build group member cache for hover tooltips (single request instead of N+1)
  const { items: groups } = await getGroupsWithMembers({ limit: 500 })
  groupsMap.value = Object.fromEntries(groups.map(g => [g.id, g]))
  // Seed serial status; WS pushes updates after this
  try { store.applySerialStatus(await getSerialStatus()) } catch { /* port not configured */ }

  const m = map()
  if (m) m.on('moveend', scheduleWeatherFetch)

  // HQ comes from the database. A failure shows an amber note with a retry; the map and live
  // data do not depend on it.
  await loadSettings()

  tickTimer = setInterval(() => { nowTick.value = Date.now() }, 10_000)
})

// Redraw only when the point moves, not on every settings save.
watch(hqLocation, (v) => { if (!v) hqClearAsk.value = false })
watch(() => hqLocation.value && `${hqLocation.value.lat},${hqLocation.value.lon}`,
  () => setHQ(hqLocation.value), { immediate: true })

onUnmounted(() => {
  clearTimeout(weatherTimer)
  clearInterval(tickTimer)
  stopWindAnim()
  const m = map()
  if (m) m.un('moveend', scheduleWeatherFetch)
  // The popup overlay belongs to this view; do not leave it on a map that outlives it.
  onFireFeatureClick(null)
  onTrackerClick(null)
  onMapContextMenu(null)
  closeContextMenu()
  if (fireOverlay) fireMap?.removeOverlay(fireOverlay)
  if (focusOverlay) fireMap?.removeOverlay(focusOverlay)
  clearTimeout(focusRingTimer)
  fireOverlay = null
  focusOverlay = null
  fireMap = null
})

function switchBasemap(id) {
  activeBasemap.value = id
  setBasemap(id)
  if (id !== 'satellite' && weatherLayerId.value) {
    weatherLayerId.value = null
    setWeatherLayer(null)
  }
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
  setMeasureMode(measureOn.value)
}
function toggleHQMode() {
  hqMode.value = !hqMode.value
  if (hqMode.value && measureOn.value) {
    measureOn.value = false
    setMeasureMode(false)
  }
  setHQPlacementMode(hqMode.value)
}
function clearHQ() {
  hqClearAsk.value = false
  saveHQ(() => settingsStore.clearHQ())
  if (hqMode.value) {
    hqMode.value = false
    setHQPlacementMode(false)
  }
}
function toggleWeather(id) {
  weatherLayerId.value = weatherLayerId.value === id ? null : id
  const url = weatherLayerId.value
    ? `https://tile.openweathermap.org/map/${weatherLayerId.value}/{z}/{x}/{y}.png?appid=${OWM_KEY}`
    : null
  setWeatherLayer(url, recolorFor(weatherLayerId.value))
  if (!weatherLayerId.value) weatherInfo.value = null
  else if (weatherLayerId.value !== 'wind_new') fetchWeather()
}

function scheduleWeatherFetch() {
  if (!weatherLayerId.value) return
  clearTimeout(weatherTimer)
  weatherTimer = setTimeout(
    () => weatherLayerId.value === 'wind_new' ? fetchWindField() : fetchWeather(),
    700
  )
}

async function fetchWeather() {
  if (!weatherLayerId.value) return
  const m = map()
  if (!m) return
  const [lon, lat] = toLonLat(m.getView().getCenter())
  try {
    const r = await fetch(
      `https://api.openweathermap.org/data/2.5/weather?lat=${lat.toFixed(4)}&lon=${lon.toFixed(4)}&appid=${OWM_KEY}&units=metric`
    )
    const d = await r.json()
    weatherInfo.value = weatherFromOwm(d)
  } catch { /* network unavailable */ }
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
      const r = await fetch(
        `https://api.openweathermap.org/data/2.5/box/city?bbox=${minLon.toFixed(2)},${minLat.toFixed(2)},${maxLon.toFixed(2)},${maxLat.toFixed(2)},${zoom}&appid=${OWM_KEY}&units=metric&cnt=50`
      )
      if (r.status === 401 || r.status === 403) boxCityDenied = true
      const d = r.ok ? await r.json() : null
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
  if (!canvas || weatherLayerId.value !== 'wind_new') { stopWindAnim(); return }
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

watch(weatherLayerId, async (id) => {
  stopWindAnim()
  if (id === 'wind_new') {
    await nextTick()
    startWindAnim()
    fetchWindField()
  }
})
// "Show on map" from a fire alarm (FireAlarmBanner). The view is kept alive, so a request can
// land while it is hidden: it waits until the map is on screen, then centres once and is cleared.
const mapActive = ref(false)
function consumeFireFocus() {
  const req = fireStore.focusRequest
  const m = map()
  if (!req || !m || !mapActive.value) return
  fireStore.clearFocusRequest()
  // The fire is drawn on the hotspots layer, which is off by default: centring on it with the
  // layer off showed an empty map, as if the button did nothing.
  ensureLayer('hotspots')
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const center = fromLonLat([req.longitude, req.latitude])
  m.updateSize()
  m.getView().animate({ center, zoom: 12, duration: reduce ? 0 : 500 })
  // Mark the spot itself, so it is found at once even before the hotspot data has drawn.
  focusOverlay?.setPosition(center)
  focusRingKey.value++
  clearTimeout(focusRingTimer)
  focusRingTimer = setTimeout(() => { focusRingKey.value = 0; focusOverlay?.setPosition(undefined) }, FOCUS_RING_MS)
}
watch(() => fireStore.focusRequest, consumeFireFocus)
onActivated(() => { mapActive.value = true; nextTick(consumeFireFocus) })
onDeactivated(() => { mapActive.value = false })

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


.serial-status {
  position: absolute; top: 12px; right: 12px; z-index: 50;
  display: flex; align-items: center; gap: 6px;
  background: var(--bg-panel); border: 1px solid var(--border);
  border-radius: 4px; padding: 4px 10px; font-size: 11px; color: var(--text-muted);
}
.serial-ok  { border-color: var(--success); color: var(--success); }
.serial-off { border-color: var(--danger);  color: var(--danger); }
.serial-dot {
  width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;
  background: currentColor;
}
.serial-ok .serial-dot { animation: sos-pulse-border .none; box-shadow: 0 0 4px currentColor; }

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
.bm-btn-weather.active { background: #0369a1; border-color: #0369a1; }
.bm-btn-danger { color: #f87171; border-color: rgba(248,113,113,0.35); }
.bm-btn-danger:hover { background: rgba(248,113,113,0.1); color: #fca5a5; }
.bm-hq-error { font-size: 12px; color: var(--warning); align-self: center; }
.bm-hq-confirm, .bm-hq-note { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; align-self: center; }
.bm-hq-confirm { color: var(--text); }
.bm-hq-note { color: var(--warning); }
.bm-btn:disabled { opacity: .45; cursor: not-allowed; }
.bm-row-break { flex-basis: 100%; height: 0; }

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

.map-context {
  position: absolute; z-index: 65; min-width: 180px; padding: 4px;
  background: var(--bg-panel); border: 1px solid var(--border); border-radius: 8px;
  box-shadow: 0 4px 18px rgba(0, 0, 0, .55);
}
.mc-item {
  display: block; width: 100%; text-align: left; padding: 9px 12px; min-height: 36px;
  background: transparent; color: var(--text); font-size: 13px; font-weight: 600; border-radius: 6px;
}
.mc-item:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; background: var(--bg-card); }
@media (hover: hover) and (pointer: fine) { .mc-item:hover { background: var(--bg-card); opacity: 1; } }

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
  .stale-feed-dot { animation: none; }
  .fire-focus-ring { animation: none; }
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
