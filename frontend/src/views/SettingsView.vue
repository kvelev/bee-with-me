<template>
  <div class="page">
    <div class="page-header"><h2>{{ t('settings.title') }}</h2></div>

    <p v-if="!store.settings && !loadFailed" class="muted">{{ t('settings.loading') }}</p>
    <div v-else-if="!store.settings" class="card">
      <p class="msg-warn" role="alert">{{ t('settings.loadFailed') }}</p>
      <button class="secondary" @click="load">{{ t('settings.retry') }}</button>
    </div>

    <form v-else class="stack" novalidate @submit.prevent="onSave">
      <section class="card">
        <h3 class="section-title">{{ t('settings.fireAlarm') }}</h3>

        <div class="alarm-block">
          <label class="toggle">
            <input v-model="draft.is_hq_alarm_enabled" type="checkbox" />
            <span class="toggle-name">{{ t('settings.hqAlarm') }}</span>
            <span :class="['state', draft.is_hq_alarm_enabled ? 'state-on' : 'state-off']">
              {{ draft.is_hq_alarm_enabled ? t('settings.stateOn') : t('settings.stateOff') }}
            </span>
          </label>
          <p class="hint">{{ t('settings.hqAlarmHint') }}</p>
          <p v-if="!draft.is_hq_alarm_enabled" class="notice" role="status">{{ t('settings.hqOffNotice') }}</p>
          <div class="field">
            <label for="hq-radius">{{ t('settings.radius') }}</label>
            <div class="with-unit">
              <input id="hq-radius" v-model="draft.hq_radius_km" type="number" inputmode="decimal"
                     step="0.1" min="0.1" max="100" :aria-invalid="!!errors.hq_radius_km"
                     aria-describedby="hq-radius-err" />
              <span class="unit">{{ t('settings.unitKm') }}</span>
            </div>
            <p id="hq-radius-err" class="field-error">{{ errors.hq_radius_km ? t('settings.' + errors.hq_radius_km) : '' }}</p>
          </div>
        </div>

        <div class="alarm-block">
          <label class="toggle">
            <input v-model="draft.is_rescuer_alarm_enabled" type="checkbox" />
            <span class="toggle-name">{{ t('settings.rescuerAlarm') }}</span>
            <span :class="['state', draft.is_rescuer_alarm_enabled ? 'state-on' : 'state-off']">
              {{ draft.is_rescuer_alarm_enabled ? t('settings.stateOn') : t('settings.stateOff') }}
            </span>
          </label>
          <p class="hint">{{ t('settings.rescuerAlarmHint') }}</p>
          <p v-if="!draft.is_rescuer_alarm_enabled" class="notice" role="status">{{ t('settings.rescuerOffNotice') }}</p>
          <div class="field">
            <label for="rescuer-radius">{{ t('settings.radius') }}</label>
            <div class="with-unit">
              <input id="rescuer-radius" v-model="draft.rescuer_radius_km" type="number" inputmode="decimal"
                     step="0.1" min="0.1" max="100" :aria-invalid="!!errors.rescuer_radius_km"
                     aria-describedby="rescuer-radius-err" />
              <span class="unit">{{ t('settings.unitKm') }}</span>
            </div>
            <p id="rescuer-radius-err" class="field-error">{{ errors.rescuer_radius_km ? t('settings.' + errors.rescuer_radius_km) : '' }}</p>
          </div>
        </div>

        <h3 class="section-title sub">{{ t('settings.timing') }}</h3>
        <div class="timing">
          <div class="field">
            <label for="age-window">{{ t('settings.ageWindow') }}</label>
            <div class="with-unit">
              <input id="age-window" v-model="draft.alarm_max_age_hours" type="number" inputmode="numeric"
                     step="1" min="1" max="168" :aria-invalid="!!errors.alarm_max_age_hours"
                     aria-describedby="age-err" />
              <span class="unit">{{ t('settings.unitHours') }}</span>
            </div>
            <p id="age-err" class="field-error">{{ errors.alarm_max_age_hours ? t('settings.' + errors.alarm_max_age_hours) : '' }}</p>
          </div>
          <div class="field">
            <label for="repeat">{{ t('settings.repeat') }}</label>
            <div class="with-unit">
              <input id="repeat" v-model="draft.repeat_minutes" type="number" inputmode="numeric"
                     step="1" min="1" max="60" :aria-invalid="!!errors.repeat_minutes"
                     aria-describedby="repeat-err" />
              <span class="unit">{{ t('settings.unitMinutes') }}</span>
            </div>
            <p id="repeat-err" class="field-error">{{ errors.repeat_minutes ? t('settings.' + errors.repeat_minutes) : '' }}</p>
          </div>
        </div>
      </section>

      <section class="card">
        <h3 class="section-title">{{ t('settings.mapDisplay') }}</h3>
        <label class="toggle">
          <input v-model="draft.is_rescuer_photo_on_map_enabled" type="checkbox" aria-describedby="photo-hint" />
          <span class="toggle-name">{{ t('settings.photosOnMap') }}</span>
        </label>
        <p id="photo-hint" class="hint flush-bottom">{{ t('settings.photosOnMapHint') }}</p>
      </section>

      <section class="card">
        <h3 class="section-title">{{ t('settings.hqTitle') }}</h3>
        <p v-if="store.hq" class="coords">{{ store.hq.lat.toFixed(5) }}, {{ store.hq.lon.toFixed(5) }}</p>
        <p v-else class="muted">{{ t('settings.hqNone') }}</p>
        <p v-if="!store.hq && draft.is_hq_alarm_enabled" class="notice flush" role="status">{{ t('settings.hqMissingNotice') }}</p>

        <div v-if="store.hq" class="row">
          <button v-if="!confirmClear" type="button" class="danger" @click="confirmClear = true">
            {{ t('settings.hqClear') }}
          </button>
          <template v-else>
            <span class="confirm-text">{{ t('settings.hqClearConfirm') }}</span>
            <button type="button" class="danger" :disabled="busy" @click="onClearHQ">{{ t('settings.hqClearYes') }}</button>
            <button type="button" class="secondary" @click="confirmClear = false">{{ t('settings.cancel') }}</button>
          </template>
        </div>
      </section>

      <div v-if="confirmOff.length" class="confirm-off" role="alertdialog" aria-labelledby="confirm-off-title">
        <p id="confirm-off-title" class="confirm-title">{{ t('settings.confirmOffTitle') }}</p>
        <p v-if="confirmOff.includes('hq')">{{ t('settings.hqOffNotice') }}</p>
        <p v-if="confirmOff.includes('rescuer')">{{ t('settings.rescuerOffNotice') }}</p>
        <div class="row">
          <button type="button" class="warn" :disabled="busy" @click="doSave">{{ t('settings.confirmOffYes') }}</button>
          <button type="button" class="secondary" @click="confirmOff = []">{{ t('settings.cancel') }}</button>
        </div>
      </div>

      <div class="actions">
        <button type="submit" :disabled="!valid || !dirty || busy">
          {{ busy ? t('settings.saving') : t('settings.save') }}
        </button>
        <button v-if="dirty" type="button" class="secondary" :disabled="busy" @click="reset">
          {{ t('settings.discard') }}
        </button>
        <span v-if="saveState === 'ok'" class="msg-ok" role="status">{{ t('settings.saved') }}</span>
        <span v-if="saveState === 'fail'" class="msg-warn" role="alert">{{ t('settings.saveFailed') }}</span>
        <span v-if="saveState === 'stale'" class="msg-warn" role="alert">{{ t('settings.saveStale') }}</span>
        <span v-if="saveState === 'missing'" class="msg-warn" role="alert">{{ t('settings.saveMissing') }}</span>
        <span v-if="saveState === 'check'" class="msg-warn" role="alert">{{ t('settings.checkFailed') }}</span>
        <span v-if="saveState === 'clean'" class="msg-note" role="status">{{ t('settings.nothingToSave') }}</span>
      </div>
    </form>

    <!-- Alarm targets: what the fire alarm can actually watch right now. Independent of the settings form. -->
    <section class="card targets" aria-labelledby="targets-title">
      <h3 id="targets-title" class="section-title">{{ t('settings.targets.title') }}</h3>
      <p v-if="targets === undefined" class="muted flush">{{ t('settings.zones.loading') }}</p>
      <p v-else-if="targets === null" class="msg-warn" role="status" data-testid="targets-unavailable">{{ t('settings.targets.unavailable') }}</p>
      <dl v-else class="target-rows">
        <div class="target-row">
          <dt>{{ t('settings.targets.hq') }}</dt>
          <dd data-testid="targets-hq">{{ targets.hq ? t('settings.targets.hqSet') : t('settings.targets.hqNotSet') }}</dd>
        </div>
        <div class="target-row">
          <dt>{{ t('settings.targets.rescuers') }}</dt>
          <dd class="mono" data-testid="targets-rescuers">{{ targets.rescuers }}</dd>
        </div>
      </dl>
      <p v-if="rescuerAlarmBlind" class="notice flush" role="status" data-testid="targets-warning">{{ t('settings.targets.noRescuers') }}</p>
    </section>

    <section class="card zones" aria-labelledby="zones-title">
      <h3 id="zones-title" class="section-title">{{ t('settings.zones.title') }}</h3>
      <p class="hint flush">{{ t('settings.zones.hint') }}</p>

      <p v-if="zonesLoading && !fire.zones.length" class="muted flush">{{ t('settings.zones.loading') }}</p>
      <div v-else-if="fire.zonesFailed" class="zones-failed">
        <p class="msg-warn" role="alert">{{ t('settings.zones.loadFailed') }}</p>
        <button type="button" class="secondary" @click="loadZones">{{ t('settings.zones.retry') }}</button>
      </div>
      <p v-else-if="!zoneList.length" class="muted flush" data-testid="zones-empty">{{ t('settings.zones.empty') }}</p>

      <ul v-if="zoneList.length" class="zone-list">
        <li v-for="z in zoneList" :key="z.id" class="zone-item" :class="{ 'zone-off': !z.is_active }" data-testid="zone-item">
          <div v-if="editingId === z.id" class="zone-edit">
            <div v-if="editStale" class="zone-stale" data-testid="zone-stale">
              <p class="msg-warn flush" role="alert">{{ t('fire.errors.zoneStale') }}</p>
              <button type="button" class="secondary" data-testid="zone-reload" @click="reloadEdit(z)">{{ t('settings.zones.reloadValues') }}</button>
            </div>
            <SuppressionZoneForm
              :key="editFormKey"
              inline mode="edit"
              :initial="editSnapshot"
              :busy="zoneBusy"
              :locked="editStale"
              :error-text="zoneError"
              @submit="onZoneSave(z, $event)"
              @cancel="stopEdit"
            />
          </div>
          <template v-else>
            <div class="zone-main">
              <div class="zone-name">
                <span class="zone-label">{{ z.label }}</span>
                <span :class="['state', z.is_active ? 'state-on' : 'state-off']">{{ z.is_active ? t('settings.zones.active') : t('settings.zones.disabled') }}</span>
              </div>
              <div class="zone-facts">
                <span class="mono">{{ t('settings.zones.radiusValue', { n: z.radius_m }) }}</span>
                <span class="mono">{{ Number(z.latitude).toFixed(5) }}, {{ Number(z.longitude).toFixed(5) }}</span>
              </div>
              <p v-if="z.notes" class="zone-notes">{{ z.notes }}</p>
              <p v-if="rowError?.id === z.id" class="msg-warn" role="alert">{{ rowError.text }}</p>
            </div>
            <div v-if="isAdmin" class="zone-actions">
              <button type="button" class="secondary" data-testid="zone-edit" :disabled="zoneBusy" @click="startEdit(z)">{{ t('settings.zones.edit') }}</button>
              <button v-if="z.is_active" type="button" class="secondary" data-testid="zone-disable" :disabled="zoneBusy" @click="onZoneDisable(z)">{{ t('settings.zones.disable') }}</button>
              <button v-else type="button" class="secondary" data-testid="zone-enable" :disabled="zoneBusy" @click="onZoneEnable(z)">{{ t('settings.zones.enable') }}</button>
            </div>
          </template>
        </li>
      </ul>
      <p v-if="zoneList.some(z => !z.is_active)" class="hint flush zones-note" data-testid="zones-disabled-note">{{ t('settings.zones.disabledNote') }}</p>
    </section>

    <TestModeCard v-if="isAdmin" />

    <!-- Outside the load/save states above: signing out must work even when settings failed to load. -->
    <section class="card account" aria-labelledby="account-title">
      <h3 id="account-title" class="section-title">{{ t('settings.account') }}</h3>
      <p v-if="auth.user?.full_name" class="who">{{ t('settings.signedInAs', { name: auth.user.full_name }) }}</p>
      <div class="row">
        <button type="button" class="secondary" data-test="logout" @click="onLogout">{{ t('settings.logout') }}</button>
        <span class="hint-inline">{{ t('settings.logoutHint') }}</span>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, inject, nextTick, onMounted, ref, watch } from 'vue'
import { routerKey } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useSettingsStore } from '../stores/settings'
import { useAuthStore } from '../stores/auth'
import { useFireStore } from '../stores/fire'
import { getFireStatus } from '../api'
import { detailOf } from '../api/client'
import { fireErrorKey } from '../lib/fireErrors'
import SuppressionZoneForm from '../components/SuppressionZoneForm.vue'
import TestModeCard from '../components/TestModeCard.vue'
import { LIMITS, alarmsTurnedOff, kmError, kmToM, mToKm, photosOnMapOf, wholeError } from '../lib/settingsForm'

const { t } = useI18n()
const store = useSettingsStore()
const auth = useAuthStore()
const fire = useFireStore()
const router = inject(routerKey, null)
const isAdmin = computed(() => auth.user?.role === 'admin')

const draft = ref({})
const loadFailed = ref(false)
const busy = ref(false)
const saveState = ref('')
const confirmOff = ref([])
const confirmClear = ref(false)

function draftFrom(s) {
  return {
    is_hq_alarm_enabled: s.is_hq_alarm_enabled,
    is_rescuer_alarm_enabled: s.is_rescuer_alarm_enabled,
    hq_radius_km: mToKm(s.hq_radius_m),
    rescuer_radius_km: mToKm(s.rescuer_radius_m),
    alarm_max_age_hours: s.alarm_max_age_hours,
    repeat_minutes: s.repeat_minutes,
    is_rescuer_photo_on_map_enabled: photosOnMapOf(s),
  }
}

// What the form showed when it last matched the server. A field still equal to it is
// untouched, so a fresher server value may replace it; an edited field is never overwritten.
let baseline = null

function reset() {
  const s = store.settings
  if (!s) return
  baseline = draftFrom(s)
  draft.value = { ...baseline }
  confirmOff.value = []
}

// After any refetch: adopt the server's values for untouched fields only, so a slow load
// cannot wipe what the operator already typed, and a stale page cannot carry old values back.
function adoptFresh() {
  const s = store.settings
  if (!s) return
  if (!baseline) { reset(); return }
  const fresh = draftFrom(s)
  const next = { ...draft.value }
  for (const k of Object.keys(fresh)) {
    if (Object.is(draft.value[k], baseline[k])) next[k] = fresh[k]
  }
  baseline = fresh
  draft.value = next
}

async function load() {
  loadFailed.value = false
  try {
    await store.fetchSettings()
    adoptFresh()
  } catch {
    loadFailed.value = true
  }
}
onMounted(() => { if (store.settings) reset(); load(); loadZones(); loadTargets() })

// ---- Alarm targets: what GET /api/fire/status says the alarm can watch right now ----------------
// undefined = loading, null = unavailable (request failed, or the server has no settings row).
const targets = ref(undefined)
async function loadTargets() {
  try {
    const status = await getFireStatus()
    targets.value = status?.targets ?? null
  } catch {
    targets.value = null
  }
}
// The rescuer alarm is on but there is nothing for it to watch: say so (amber, not red).
const rescuerAlarmBlind = computed(() =>
  !!store.settings?.is_rescuer_alarm_enabled && !!targets.value && targets.value.rescuers === 0)

// ---- Suppression zones ------------------------------------------------------------------------
// Disabled zones are listed too (the server removes them after 48 h), so an operator can bring one back.
const zonesLoading = ref(true)
const editingId = ref(null)
const zoneBusy = ref(false)
const zoneError = ref('')      // shown inside the open edit form
const rowError = ref(null)     // { id, text } for a disable / re-enable that failed

const zoneList = computed(() => [...fire.zones].sort((a, b) =>
  Number(b.is_active) - Number(a.is_active) || String(a.label).localeCompare(String(b.label))))

async function loadZones() {
  zonesLoading.value = true
  try { await fire.fetchZones(true) } catch { /* fire.zonesFailed drives the retry notice */ } finally { zonesLoading.value = false }
}

// An edit carries the version the form was opened on (B54): a push that refetches the zone while
// the form is open must never pair newer server data with the operator's older values.
const editingVersion = ref(null)
const editSnapshot = ref({})   // the values the open form started from
const editFormKey = ref(0)     // bumped to rebuild the form from fresh values
const editStale = computed(() => {
  if (editingId.value == null) return false
  const cur = fire.zones.find(z => z.id === editingId.value)
  return !!cur && cur.updated_at !== editingVersion.value
})

function startEdit(z) {
  editingId.value = z.id; editingVersion.value = z.updated_at; editSnapshot.value = { ...z }
  editFormKey.value++; zoneError.value = ''; rowError.value = null
}
function stopEdit() { editingId.value = null; editingVersion.value = null; zoneError.value = '' }
// Reload the current server values into the form (drops the operator's unsaved typing).
function reloadEdit(z) {
  editingVersion.value = z.updated_at; editSnapshot.value = { ...z }; editFormKey.value++; zoneError.value = ''
}

// Edits send the version the form opened on; it never carries is_active (activation has its own endpoints).
const zoneBody = (z, over = {}) => ({
  label: z.label, latitude: z.latitude, longitude: z.longitude, radius_m: z.radius_m, notes: z.notes ?? null,
  expected_updated_at: z.updated_at, ...over,
})

async function runZoneAction(id, action, onError) {
  if (zoneBusy.value) return
  zoneBusy.value = true
  try {
    await action()
    return true
  } catch (err) {
    const text = t(fireErrorKey(err))
    if (err?.status === 409 && err?.detail === 'zone_stale') {
      // Someone changed the zone: pull the current list, close any edit form (its values are out of date)
      // and say so on the row. The operator reopens Edit on the fresh values.
      await loadZones()
      stopEdit()
      rowError.value = { id, text }
    } else {
      onError(text)
    }
  } finally {
    zoneBusy.value = false
  }
}

async function onZoneSave(z, values) {
  if (editStale.value) return   // the notice is showing: reload the values first
  zoneError.value = ''
  const body = zoneBody(editSnapshot.value, { ...values, expected_updated_at: editingVersion.value })
  const ok = await runZoneAction(z.id, () => fire.updateZone(z.id, body), (text) => { zoneError.value = text })
  if (ok) stopEdit()
}
async function onZoneDisable(z) {
  rowError.value = null
  await runZoneAction(z.id, () => fire.disableZone(z.id, z.updated_at), (text) => { rowError.value = { id: z.id, text } })
}
async function onZoneEnable(z) {
  rowError.value = null
  await runZoneAction(z.id, () => fire.enableZone(z.id, z.updated_at), (text) => { rowError.value = { id: z.id, text } })
}

const errors = computed(() => ({
  hq_radius_km:        kmError(draft.value.hq_radius_km),
  rescuer_radius_km:   kmError(draft.value.rescuer_radius_km),
  alarm_max_age_hours: wholeError(draft.value.alarm_max_age_hours, LIMITS.hours, 'errRangeHours'),
  repeat_minutes:      wholeError(draft.value.repeat_minutes, LIMITS.minutes, 'errRangeMinutes'),
}))
const valid = computed(() => Object.values(errors.value).every(e => !e))

const patch = computed(() => ({
  is_hq_alarm_enabled: !!draft.value.is_hq_alarm_enabled,
  is_rescuer_alarm_enabled: !!draft.value.is_rescuer_alarm_enabled,
  hq_radius_m: kmToM(draft.value.hq_radius_km),
  rescuer_radius_m: kmToM(draft.value.rescuer_radius_km),
  alarm_max_age_hours: Number(draft.value.alarm_max_age_hours),
  repeat_minutes: Number(draft.value.repeat_minutes),
  is_rescuer_photo_on_map_enabled: draft.value.is_rescuer_photo_on_map_enabled !== false,
}))
const dirty = computed(() => {
  const s = store.settings
  if (!s) return false
  const server = { ...s, is_rescuer_photo_on_map_enabled: photosOnMapOf(s) }
  return Object.entries(patch.value).some(([k, v]) => server[k] !== v)
})

// The decision to ask "turn off alarms?" is made against the server's state right now, not
// against what this page loaded earlier (BP-02): a stale page cannot switch an alarm off
// without the confirmation.
async function onSave() {
  if (busy.value || !valid.value || !dirty.value) return
  saveState.value = ''
  busy.value = true
  try {
    await store.fetchSettings()
  } catch {
    busy.value = false
    saveState.value = 'check'   // nothing was sent: say so, do not claim a failed save
    return
  }
  adoptFresh()
  busy.value = false
  await nextTick()
  if (!valid.value) return
  if (!dirty.value) {           // the fresh server state already equals the form
    await nextTick()            // the draft watcher clears saveState; set it after
    saveState.value = 'clean'
    return
  }
  const off = alarmsTurnedOff(store.settings, patch.value)
  if (off.length) { confirmOff.value = off; return }
  doSave()
}

function failState(err) {
  if (detailOf(err) === 'settings_stale') return 'stale'
  if (detailOf(err) === 'settings_missing') return 'missing'
  return 'fail'
}

async function doSave() {
  busy.value = true
  confirmOff.value = []
  try {
    await store.saveSettings(patch.value)
    reset()
    saveState.value = 'ok'
  } catch (err) {
    const state = failState(err)
    if (state === 'stale') adoptFresh()   // the store already reloaded; keep the operator's edits
    await nextTick()                      // the draft watcher clears saveState; set it after
    saveState.value = state
  } finally {
    busy.value = false
  }
}

async function onClearHQ() {
  busy.value = true
  saveState.value = ''
  try {
    await store.clearHQ()
    confirmClear.value = false
  } catch (err) {
    saveState.value = failState(err)
  } finally {
    busy.value = false
  }
}

// Same logic the sidebar button had: the auth store clears the session, then back to the login page.
function onLogout() {
  auth.logout()
  router?.push('/login')
}

// Any edit hides a stale result; the confirm step goes away if the edit undoes the switch-off.
watch(draft, () => {
  saveState.value = ''
  if (confirmOff.value.length && !alarmsTurnedOff(store.settings, patch.value).length) confirmOff.value = []
}, { deep: true })
</script>

<style scoped>
.page { padding: 24px; flex: 1; max-width: 720px; }
.stack { display: flex; flex-direction: column; gap: 16px; }
.account { margin-top: 16px; }
.targets, .zones { margin-top: 16px; }
.hint.flush { margin-left: 0; }
.hint.flush-bottom { margin-bottom: 0; }
.muted.flush { margin-bottom: 0; }
.mono { font-family: ui-monospace, monospace; font-weight: 600; font-variant-numeric: tabular-nums; }
.target-rows { display: flex; flex-direction: column; gap: 6px; font-size: 14px; }
.target-row { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; }
.target-row dt { color: var(--text-muted); font-size: 13px; }
.target-row + .target-row { padding-top: 6px; border-top: 1px solid var(--border); }
.targets .notice { margin-top: 12px; margin-bottom: 0; }

.zones .hint { margin-bottom: 12px; }
.zones-failed { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.zone-list { list-style: none; display: flex; flex-direction: column; }
.zone-item { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 12px 0; }
.zone-item + .zone-item { border-top: 1px solid var(--border); }
.zone-item > :only-child { flex: 1; }
.zone-main { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 4px; }
.zone-name { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.zone-label { font-size: 14px; font-weight: 600; overflow-wrap: anywhere; }
.zone-off .zone-label, .zone-off .zone-facts, .zone-off .zone-notes { color: var(--text-muted); }
.zone-facts { display: flex; gap: 6px 16px; flex-wrap: wrap; font-size: 12px; color: var(--text-muted); }
.zone-notes { font-size: 13px; color: var(--text-muted); white-space: pre-wrap; overflow-wrap: anywhere; max-height: 4.2em; overflow-y: auto; }
.zone-edit { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 8px; }
.zone-stale { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.zone-actions { display: flex; gap: 8px; flex-shrink: 0; flex-wrap: wrap; justify-content: flex-end; }
.zone-actions button { padding: 6px 12px; font-size: 13px; }
.zones .zones-note { margin-top: 8px; margin-bottom: 0; }
.who { font-size: 14px; margin-bottom: 4px; }
.hint-inline { font-size: 13px; color: var(--text-muted); }
.section-title { font-size: 14px; font-weight: 600; margin-bottom: 16px; color: var(--text-muted); }
.section-title.sub { margin-top: 8px; }
.muted { font-size: 13px; color: var(--text-muted); margin-bottom: 12px; }
.hint { font-size: 13px; color: var(--text-muted); margin: 4px 0 10px 28px; }

.alarm-block { padding-bottom: 16px; margin-bottom: 16px; border-bottom: 1px solid var(--border); }

.toggle { display: flex; align-items: center; gap: 10px; margin: 0; font-size: 14px; color: var(--text); cursor: pointer; }
.toggle input { width: 18px; height: 18px; padding: 0; accent-color: var(--accent); flex-shrink: 0; }
.toggle-name { font-weight: 600; }
.state { font-size: 11px; font-weight: 700; letter-spacing: .06em; padding: 2px 8px; border-radius: 99px; }
.state-on  { color: var(--text-muted); border: 1px solid var(--border); }
.state-off { color: var(--warning); border: 1px solid var(--warning); background: var(--warning-wash); }

.notice {
  margin: 0 0 12px 28px; padding: 8px 12px; font-size: 13px;
  color: var(--text); background: var(--warning-wash);
  border: 1px solid var(--warning-line); border-radius: 6px;
}
.notice.flush { margin-left: 0; }

.field { margin-left: 28px; max-width: 220px; }
.field label { margin-bottom: 4px; }
.with-unit { display: flex; align-items: center; gap: 8px; }
.with-unit input { font-family: ui-monospace, monospace; font-weight: 600; }
.unit { font-size: 13px; color: var(--text-muted); min-width: 28px; }
.field-error { min-height: 18px; margin-top: 4px; font-size: 12px; color: var(--warning); }
input[aria-invalid="true"] { border-color: var(--warning); }

.timing { display: grid; grid-template-columns: 1fr 1fr; gap: 0 20px; }
.timing .field { margin-left: 0; max-width: none; }

.coords { font-family: ui-monospace, monospace; font-size: 13px; font-weight: 600; margin-bottom: 12px; }
.row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-top: 8px; }
.confirm-text { font-size: 13px; }

.confirm-off {
  padding: 14px 16px; border: 1px solid var(--warning-line); border-radius: 10px;
  background: var(--warning-wash); font-size: 14px;
}
.confirm-off p + p { margin-top: 6px; }
.confirm-title { font-weight: 700; }
button.warn { background: var(--warning-wash); border: 1px solid var(--warning); color: var(--text); }

.actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
button:disabled { opacity: .45; cursor: not-allowed; }
.msg-ok { font-size: 13px; color: var(--success); }
.msg-warn { font-size: 13px; color: var(--warning); }
.msg-note { font-size: 13px; color: var(--text-muted); }

@media (max-width: 600px) {
  .timing { grid-template-columns: 1fr; }
  .zone-item { flex-direction: column; }
  .zone-actions { justify-content: flex-start; }
}
</style>
