<template>
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
</template>

<script setup>
// The suppression-zones section of the Settings page (host `settings`): list, edit, disable and re-enable.
// Moved here from SettingsView.vue with its markup, classes, test ids and texts (the settings.* keys) unchanged.
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import SuppressionZoneForm from './SuppressionZoneForm.vue'
import { fireErrorKey } from '../lib/fireErrors.js'
import { useFireStore } from '../store.js'

const props = defineProps({ context: { type: Object, default: undefined } })

const { t } = useI18n()
const fire = useFireStore()
const isAdmin = computed(() => !!props.context?.isAdmin)

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
onMounted(loadZones)

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
</script>

<style scoped>
.zones { margin-top: 16px; }
.section-title { font-size: 14px; font-weight: 600; margin-bottom: 16px; color: var(--text-muted); }
.hint { font-size: 13px; color: var(--text-muted); margin: 4px 0 10px 28px; }
.hint.flush { margin-left: 0; }
.muted { font-size: 13px; color: var(--text-muted); margin-bottom: 12px; }
.muted.flush { margin-bottom: 0; }
.mono { font-family: ui-monospace, monospace; font-weight: 600; font-variant-numeric: tabular-nums; }
.msg-warn { font-size: 13px; color: var(--warning); }
.state { font-size: 11px; font-weight: 700; letter-spacing: .06em; padding: 2px 8px; border-radius: 99px; }
.state-on  { color: var(--text-muted); border: 1px solid var(--border); }
.state-off { color: var(--warning); border: 1px solid var(--warning); background: var(--warning-wash); }
button:disabled { opacity: .45; cursor: not-allowed; }

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

@media (max-width: 600px) {
  .zone-item { flex-direction: column; }
  .zone-actions { justify-content: flex-start; }
}
</style>
