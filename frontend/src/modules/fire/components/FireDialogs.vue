<template>
  <FieldReportForm
    v-if="ui.dialog?.kind === 'report'"
    :target="ui.dialog.target"
    :busy="dialogBusy"
    :error-text="dialogError"
    @submit="submitReport"
    @cancel="closeDialog"
  />
  <SuppressionZoneForm
    v-if="ui.dialog?.kind === 'zone'"
    :latitude="ui.dialog.target.latitude"
    :longitude="ui.dialog.target.longitude"
    :busy="dialogBusy"
    :error-text="dialogError"
    @submit="submitZone"
    @cancel="closeDialog"
  />
</template>

<script setup>
// The field-report and suppression-zone dialogs as a fire map panel (host `map`). The open dialog lives in
// useFireUi (`{ kind: 'report' | 'zone', target }`), so any contribution can open one.
import { defineAsyncComponent, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { fireErrorKey } from '../lib/fireErrors.js'
import { useFireStore } from '../store.js'
import { useFireUi } from '../ui.js'

const FieldReportForm = defineAsyncComponent(() => import('./FieldReportForm.vue'))
const SuppressionZoneForm = defineAsyncComponent(() => import('./SuppressionZoneForm.vue'))

const props = defineProps({
  context: { type: Object, required: true },
})

const { t } = useI18n()
const fireStore = useFireStore()
const ui = useFireUi()

const dialogBusy = ref(false)
const dialogError = ref('')
let dialogSeq = 0

// A dialog that opens (or replaces the present one, or closes) discards whatever the previous one was waiting
// for. The watcher is synchronous so a stale answer cannot slip in between the change and the reset.
watch(() => ui.dialog, (next) => {
  dialogSeq++
  dialogBusy.value = false
  dialogError.value = ''
  if (next) props.context.closeContextMenu?.()
}, { flush: 'sync' })

function closeDialog() {
  ui.closeDialog()
}

// Runs a write for the open dialog. A dialog that was closed or replaced while the request was
// in flight takes neither the result nor the error.
async function runDialogAction(action, errorContext) {
  if (dialogBusy.value) return false
  const mine = ++dialogSeq
  dialogBusy.value = true
  dialogError.value = ''
  try {
    await action()
    if (mine === dialogSeq) closeDialog()
    return true
  } catch (err) {
    if (mine === dialogSeq) { dialogError.value = t(fireErrorKey(err, errorContext)); dialogBusy.value = false }
  }
  return false
}

async function submitReport({ notes }) {
  const target = ui.dialog?.target
  if (!target) return
  if (target.noPosition) return
  const body = { latitude: target.latitude, longitude: target.longitude, notes }
  // A 404 here means the running backend lacks the field-report endpoint (older than T18).
  if (await runDialogAction(() => fireStore.reportFire(body), 'report')) ui.ensureLayer('hotspots')
}

async function submitZone(values) {
  const d = ui.dialog
  if (d?.kind !== 'zone') return
  const body = { ...values, latitude: d.target.latitude, longitude: d.target.longitude }
  if (await runDialogAction(() => fireStore.createZone(body))) ui.ensureLayer('zones')
}
</script>
