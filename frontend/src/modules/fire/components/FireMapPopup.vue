<template>
  <FirePopup
    :kind="selection.kind"
    :properties="shownProperties"
    :lon-lat="lonLat"
    :is-admin="context.isAdmin.value"
    :busy="busy"
    :error-text="errorText"
    @close="emit('close')"
    @dismiss="onDismiss"
    @extinguish="onExtinguish"
    @create-zone="onCreateZone"
  />
</template>

<script setup>
// The fire popup as a map-shell contribution (`popups` in the fire manifest). The host renders it only while a
// selection exists and hands over the selection and the map context. No OpenLayers import: the overlay
// coordinate is converted to WGS84 through context.mapKit.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import FirePopup from './FirePopup.vue'
import { fireErrorKey } from '../lib/fireErrors.js'
import { useFireStore } from '../store.js'
import { useFireUi } from '../ui.js'

const props = defineProps({
  selection: { type: Object, required: true },   // { kind, properties, coordinate }
  context: { type: Object, required: true },
})
const emit = defineEmits(['close'])

const { t } = useI18n()
const fireStore = useFireStore()

const busy = ref(false)
const errorText = ref('')
// The selection is a prop and is never mutated: the server's answer to an action is kept here and shown
// instead of the copy the popup was opened with.
const override = ref(null)
const shownProperties = computed(() => override.value ?? props.selection.properties)

// A new click is a new popup: forget the previous one's server copy and error.
watch(() => props.selection, () => {
  override.value = null
  errorText.value = ''
})

// The overlay coordinate is in the map projection (EPSG:3857); the popup wants WGS84.
const lonLat = computed(() => {
  const c = props.selection.coordinate
  return Array.isArray(c) ? props.context.mapKit.toLonLat(c) : null
})

// A fire popup closes when its layer is switched off (hotspot <-> hotspots, burnt_area <-> burnt; zones never).
watch(() => fireStore.layers.hotspots, (on) => { if (!on && props.selection.kind === 'hotspot') emit('close') })
watch(() => fireStore.layers.burnt, (on) => { if (!on && props.selection.kind === 'burnt_area') emit('close') })

// Only one popup action runs at a time. The server answers with the changed row; the popup then
// shows that row (state chip, notes) instead of the copy it was opened with.
async function runPopupAction(id, action) {
  if (busy.value) return
  busy.value = true
  errorText.value = ''
  try {
    await action()
    syncPopup(id)
  } catch (err) {
    if (props.selection.properties?.id === id) errorText.value = t(fireErrorKey(err))
  } finally {
    busy.value = false
  }
}

function syncPopup(id) {
  if (props.selection.properties?.id !== id) return
  const next = fireStore.hotspots.features.find(f => f.id === id)
  if (next) override.value = { ...next.properties }
}

const onDismiss = ({ id, notes }) => runPopupAction(id, () => fireStore.dismissHotspot(id, notes))
const onExtinguish = ({ id }) => runPopupAction(id, () => fireStore.extinguish(id))
function onCreateZone() {
  const ll = lonLat.value
  if (!ll) return
  useFireUi().openDialog({ kind: 'zone', target: { latitude: ll[1], longitude: ll[0] } })
  emit('close')
}
</script>
