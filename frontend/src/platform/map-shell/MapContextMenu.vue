<template>
  <div v-if="state && items.length" ref="menuEl" class="map-context" role="menu" :style="{ left: state.x + 'px', top: state.y + 'px' }">
    <button
      v-for="item in items"
      :key="item.id"
      type="button"
      role="menuitem"
      class="mc-item"
      :data-testid="item.testId"
      @click="choose(item)"
    >
      {{ t(item.labelKey) }}
    </button>
  </div>
</template>

<script setup>
// The map's right-click / long-press menu. The items come from contributions (modules and legacy
// entries); the view calls open() with the clicked point and the size of the map, and the menu
// positions itself inside it. An item that throws is logged by id and skipped: the menu closes
// and the map stays up.
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { toLonLat } from 'ol/proj'
import { contributionProblems } from './contributions.js'

const props = defineProps({
  items: { type: Array, default: () => [] },
})

const { t } = useI18n()
const state = ref(null)   // { x, y, coordinate } | null
const menuEl = ref(null)

function logFailure(item, err) {
  console.error('[map-shell] context-menu item "%s" failed', item?.id ?? '?', err)
}

function onOutsidePointer(e) { if (!menuEl.value?.contains(e.target)) close() }
function onKey(e) { if (e.key === 'Escape') close() }

function close() {
  if (!state.value) return
  state.value = null
  document.removeEventListener('pointerdown', onOutsidePointer, true)
  document.removeEventListener('keydown', onKey, true)
}

async function open({ coordinate, pixel, bounds }) {
  if (!props.items.length) return
  const width = bounds?.width ?? 0
  const height = bounds?.height ?? 0
  // Keep the menu inside the map (about 190 x 44 px).
  const x = Math.max(4, Math.min(pixel[0], width ? width - 196 : pixel[0]))
  const y = Math.max(4, Math.min(pixel[1], height ? height - 52 : pixel[1]))
  const first = !state.value
  state.value = { x, y, coordinate }
  if (first) {
    document.addEventListener('pointerdown', onOutsidePointer, true)
    document.addEventListener('keydown', onKey, true)
  }
  await nextTick()
  menuEl.value?.querySelector('button')?.focus()
}

function choose(item) {
  const coordinate = state.value?.coordinate
  if (!coordinate) return
  try {
    const result = item.onSelect({ coordinate, lonLat: toLonLat(coordinate) })
    if (result && typeof result.catch === 'function') result.catch((err) => logFailure(item, err))
  } catch (err) {
    logFailure(item, err)
  }
  close()
}

watch(() => props.items, (items) => {
  for (const problem of contributionProblems([], { contextMenu: items })) console.error('[map-shell] %s', problem)
  if (!items.length) close()
}, { immediate: true })

onBeforeUnmount(close)

defineExpose({ open, close })
</script>

<style scoped>
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
</style>
