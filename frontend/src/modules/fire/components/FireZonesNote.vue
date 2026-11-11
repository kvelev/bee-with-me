<template>
  <span v-if="context.isAdmin.value && fireStore.layers.zones && fireStore.zonesFailed" class="bm-hq-note" role="status">
    {{ t('fire.zone.loadFailed') }}
    <button class="bm-btn" @click="retry">{{ t('fire.zone.retry') }}</button>
  </span>
</template>

<script setup>
// "Zones could not be loaded" note with a retry, rendered in the map toolbar row beside the layer buttons.
import { useI18n } from 'vue-i18n'
import { useFireStore } from '../store.js'

defineProps({ context: { type: Object, required: true } })

const { t } = useI18n()
const fireStore = useFireStore()

function retry() { fireStore.fetchZones().catch(() => { /* zonesFailed shows the note */ }) }
</script>

<style scoped>
/* Same rules as MapView's .bm-hq-note and .bm-btn (scoped CSS does not reach a child component). */
.bm-hq-note { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; align-self: center; color: var(--warning); }
.bm-btn {
  background: var(--bg-panel); border: 1px solid var(--border);
  color: var(--text-muted); padding: 5px 10px; font-size: 12px; border-radius: 4px;
}
.bm-btn:hover  { color: var(--text); }
</style>
