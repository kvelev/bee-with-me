<template>
  <div ref="el" :class="anchorClass">
    <slot v-if="shown" :popup="popup" :selection="selection" />
  </div>
</template>

<script setup>
// OpenLayers moves the anchor element into its overlay; the popup inside is a Vue component.
// One map overlay for the popups that modules contribute. The host picks the popup that claims the
// kind of the selection, renders the slot with it and anchors the overlay at the selection.
// A popup that throws is isolated: it is logged by id and renders nothing, the map stays up.
import { computed, nextTick, onBeforeUnmount, onErrorCaptured, onMounted, ref, watch } from 'vue'
import Overlay from 'ol/Overlay'
import { contributionProblems, popupFor } from './contributions.js'

const props = defineProps({
  map: { type: Object, default: null },
  popups: { type: Array, default: () => [] },
  selection: { type: Object, default: null },
  anchorClass: { type: String, default: '' },
})

const el = ref(null)
const failed = ref(false)
let overlay = null
let overlayMap = null

const popup = computed(() => (props.selection ? popupFor(props.popups, props.selection.kind) : null))
const shown = computed(() => !!props.selection && !!popup.value && !failed.value)

function fail(err) {
  failed.value = true
  console.error('[map-shell] popup "%s" failed', popup.value?.id ?? '?', err)
}

function removeOverlay() {
  if (overlay && overlayMap) overlayMap.removeOverlay(overlay)
  overlay = null
  overlayMap = null
}

// The overlay is added once the map exists and the anchor element is mounted; a map that
// changes or goes away takes the overlay off the old map first.
function syncOverlay() {
  if (overlay && overlayMap !== props.map) removeOverlay()
  if (overlay || !props.map || !el.value) return
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  overlay = new Overlay({
    element: el.value,
    positioning: 'bottom-center',
    offset: [0, -16],
    stopEvent: true,
    autoPan: { animation: { duration: reduce ? 0 : 200 }, margin: 24 },
  })
  overlayMap = props.map
  props.map.addOverlay(overlay)
  if (props.selection) schedulePosition()
}

// The popup has no size until Vue renders it; position after that so OpenLayers anchors
// it by its real width and height.
async function schedulePosition() {
  await nextTick()
  if (!overlay) return
  try {
    overlay.setPosition(shown.value ? props.selection.coordinate : undefined)
  } catch (err) {
    fail(err)
  }
}

watch(() => props.map, syncOverlay, { immediate: true, flush: 'sync' })
onMounted(syncOverlay)

watch(() => props.selection, () => {
  failed.value = false
  schedulePosition()
}, { immediate: true })

watch(() => props.popups, (popups) => {
  for (const problem of contributionProblems([], { popups })) console.error('[map-shell] %s', problem)
}, { immediate: true })

onErrorCaptured((err) => {
  fail(err)
  schedulePosition()
  return false
})

onBeforeUnmount(removeOverlay)
</script>
