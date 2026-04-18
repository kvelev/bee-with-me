<template>
  <SOSToast />
  <div class="map-layout">
    <div ref="mapEl" class="map-container" />

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
    </div>

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
    <aside class="tracker-panel">
      <div class="panel-header">
        <span>{{ t('map.trackers') }} ({{ displayList.length }})</span>
        <span v-if="store.hasSOS" class="badge badge-sos sos-pulse">SOS</span>
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
        <div
          v-for="pos in displayList" :key="pos.device_id"
          class="tracker-row"
          :class="{ 'tracker-sos': pos.sos_active }"
          @click="focusDevice(pos)"
        >
          <div class="tracker-dot" :style="{ background: pos.groups?.[0]?.color ?? '#3b82f6' }" />
          <div class="tracker-info">
            <div class="tracker-name">{{ pos.full_name || pos.device_name || pos.dev_sn }}</div>
            <div class="tracker-mgrs">{{ pos.mgrs }}</div>
          </div>
          <div class="tracker-bat" :class="batClass(pos.battery_voltage)">
            {{ pos.battery_voltage?.toFixed(1) ?? '—' }}V
          </div>
        </div>
        <div v-if="!displayList.length" class="no-trackers">{{ t('map.noTrackers') }}</div>
      </template>

      <!-- Group mode -->
      <template v-else>
        <template v-for="group in groupsWithLeaders" :key="group.id">
          <div class="group-section-header" :style="{ borderLeftColor: group.color }">
            <span class="group-section-dot" :style="{ background: group.color }" />
            {{ group.name }}
          </div>
          <div v-if="group.leader" class="tracker-row tracker-leader" @click="focusDevice(group.leader)">
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
          <div v-else class="no-leader">{{ t('map.noLeader') }}</div>
        </template>
        <div v-if="!groupsWithLeaders.length" class="no-trackers">{{ t('map.noTrackers') }}</div>
      </template>
    </aside>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { fromLonLat } from 'ol/proj'
import { useLocationsStore } from '../stores/locations'
import { useWebSocket } from '../composables/useWebSocket'
import { useMap, BASEMAPS } from '../composables/useMap'
import { getGroupsWithMembers, getSerialStatus } from '../api'
import SOSToast from '../components/SOSToast.vue'

const { t } = useI18n()
const store   = useLocationsStore()
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

const rankFiltered = computed(() => {
  const q = rankFilter.value.trim().toLowerCase()
  if (!q) return store.positionList
  return store.positionList.filter(pos => pos.rank?.toLowerCase().includes(q))
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

const { map, setBasemap, setMGRSGrid, setLatLonGrid, setTrailVisible, setCheckpointNumbers, setMeasureMode, refreshMarkers } = useMap(
  mapEl,
  displayList,
  computed(() => store.trails),
  (coords) => { cursorCoords.value = coords },
  (data)   => { measureReadout.value = data },
  groupsMap,
)
const { connect } = useWebSocket()

onMounted(async () => {
  await Promise.all([store.fetchLive(), store.fetchSOS(), store.fetchTrail()])
  connect()
  // Build group member cache for hover tooltips (single request instead of N+1)
  const groups = await getGroupsWithMembers()
  groupsMap.value = Object.fromEntries(groups.map(g => [g.id, g]))
  // Seed serial status; WS pushes updates after this
  try { store.applySerialStatus(await getSerialStatus()) } catch { /* port not configured */ }
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
  setMeasureMode(measureOn.value)
}
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
  background: rgba(29,78,216,0.15); color: #60a5fa;
  font-family: monospace; font-size: 13px; font-weight: 600;
  padding: 5px 14px; border-radius: 6px; pointer-events: none;
  border: 1px solid rgba(29,78,216,0.5); z-index: 50;
  letter-spacing: .04em;
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
