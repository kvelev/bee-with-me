<template>
  <!-- Mode toggle (bottom-right of the map, above the tracker panel) -->
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
  <aside ref="panelEl" class="tracker-panel">
    <div class="panel-header">
      <span>{{ t('map.trackers') }} ({{ displayList.length }})</span>
      <span v-if="context?.hasSOS?.value" class="badge badge-sos sos-pulse">SOS</span>
    </div>

    <!-- Devices we've stopped hearing from. Deliberately quiet: no pulse, no sound, no red,
         this is a "look at this" notice, not the SOS alarm. -->
    <div v-if="tracking.silentList.length" class="silence-notice">
      <span class="silence-dot" />
      <span class="silence-text">
        {{ t('map.silenceNotice', { n: tracking.silentList.length }) }}
        <template v-if="tracking.lostList.length">
          · {{ t('map.silenceLost', { n: tracking.lostList.length }) }}
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
          @click="selectRow(pos)"
          @keydown.enter.self.prevent="selectRow(pos)"
          @keydown.space.self.prevent="selectRow(pos)"
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
        <div v-if="selectedDeviceId === pos.device_id && actionsFor(pos).length" class="tracker-actions">
          <button
            v-for="action in actionsFor(pos)" :key="action.id"
            type="button" class="tracker-report" :data-testid="action.testId"
            @click="action.onSelect(subjectOf(pos))"
          >
            {{ t(action.labelKey) }}
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
             @click="selectRow(group.leader)"
             @keydown.enter.self.prevent="selectRow(group.leader)"
             @keydown.space.self.prevent="selectRow(group.leader)">
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
        <div v-if="group.leader && selectedDeviceId === group.leader.device_id && actionsFor(group.leader).length" class="tracker-actions">
          <button
            v-for="action in actionsFor(group.leader)" :key="action.id"
            type="button" class="tracker-report" :data-testid="action.testId"
            @click="action.onSelect(subjectOf(group.leader))"
          >
            {{ t(action.labelKey) }}
          </button>
        </div>
        <div v-if="!group.leader" class="no-leader">{{ t('map.noLeader') }}</div>
      </template>
      <div v-if="!groupsWithLeaders.length" class="no-trackers">{{ t('map.noTrackers') }}</div>
    </template>
  </aside>
</template>

<script setup>
// The tracker list and the individuals/teams switch. The map view owns the tick and the reset (see ui.js); this panel
// only reads the shared state. What it needs of the map comes through `context`: `facade` (map, refreshMarkers),
// `mapKit` (fromLonLat), `hasSOS` (a ref) and `rowActions` (the actions the modules offer for a selected row).
import { nextTick, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { ageMs, contactAt, formatAge, freshnessOf } from '../lib/freshness.js'
import { useTrackingStore } from '../store.js'
import { useTrackerUi } from '../ui.js'

const props = defineProps({ context: { type: Object, default: undefined } })

const { t } = useI18n()
const tracking = useTrackingStore()
const ui = useTrackerUi()
const { viewMode, rankFilter, selectedDeviceId, nowTick, displayList, groupsWithLeaders } = storeToRefs(ui)

const panelEl = ref(null)

function setViewMode(mode) {
  ui.viewMode = mode
  props.context?.facade?.refreshMarkers?.(ui.displayList)
}

function focusDevice(pos) {
  const m = props.context?.facade?.map?.()
  const fromLonLat = props.context?.mapKit?.fromLonLat
  if (m && fromLonLat) m.getView().animate({ center: fromLonLat([pos.longitude, pos.latitude]), zoom: 13, duration: 500 })
}

function selectRow(pos) {
  ui.select(pos.device_id)
  focusDevice(pos)
}

// The position is frozen here, at the click: the volunteer keeps moving while the operator types. The actions of the
// modules get this subject; what they make of it (the 24 hour rule of fire, for one) is theirs.
function subjectOf(pos) {
  const live = tracking.positions[pos.device_id] ?? null
  return {
    deviceId: pos.device_id,
    name: pos.full_name || pos.device_name || String(pos.dev_sn ?? ''),
    position: live,
    ageMs: live ? ageMs(live) : null,
    receivedAt: live ? contactAt(live) : null,
  }
}

function actionsFor(pos) {
  const subject = subjectOf(pos)
  return (props.context?.rowActions ?? []).filter((a) => typeof a.isAvailable !== 'function' || a.isAvailable(subject))
}

// A marker click selects the row; bring it into view.
watch(selectedDeviceId, async (id) => {
  if (!id) return
  await nextTick()
  const row = [...(panelEl.value?.querySelectorAll('[data-device-id]') ?? [])].find((el) => el.dataset.deviceId === id)
  row?.scrollIntoView?.({ block: 'nearest' })
})

function batClass(v) {
  if (v == null) return ''
  if (v >= 3.5) return 'bat-ok'
  if (v >= 3.0) return 'bat-warn'
  return 'bat-low'
}
</script>

<style scoped>
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
</style>
