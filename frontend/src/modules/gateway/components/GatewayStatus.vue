<template>
  <!-- Serial device status (top-right of the map) -->
  <div v-if="store.status" class="serial-status" :class="store.status.connected ? 'serial-ok' : 'serial-off'">
    <span class="serial-dot" />
    <span v-if="store.status.connected">
      {{ t('map.serialConnected') }} · {{ store.status.port }} · {{ store.status.frames_received }} frames
    </span>
    <span v-else>{{ t('map.serialDisconnected') }} · {{ store.status.port }}</span>
  </div>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
import { useGatewayStore } from '../store.js'

defineProps({ context: { type: Object, default: undefined } })

const { t } = useI18n()
const store = useGatewayStore()
</script>

<style scoped>
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
.serial-ok .serial-dot { animation: sos-pulse-border none; box-shadow: 0 0 4px currentColor; }
</style>
