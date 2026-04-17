<template>
  <div v-if="store.hasSOS" class="sos-banner sos-pulse">
    <span>{{ t('sos.active') }}</span>
    <span v-for="alert in store.sosAlerts" :key="alert.id" class="sos-entry">
      {{ alert.full_name || 'Unknown' }} ({{ alert.dev_sn }})
      <button class="resolve-btn" @click="resolve(alert)">{{ t('sos.resolve') }}</button>
    </span>
  </div>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
import { useLocationsStore } from '../stores/locations'

const { t } = useI18n()
const store = useLocationsStore()

async function resolve(alert) {
  await store.resolveSOS(alert.id)
}
</script>

<style scoped>
.sos-banner {
  background: var(--danger); color: #fff;
  padding: 10px 20px; display: flex; align-items: center;
  gap: 16px; flex-wrap: wrap; font-weight: 600; font-size: 14px;
  flex-shrink: 0;
}
.sos-entry { display: flex; align-items: center; gap: 8px; }
.resolve-btn {
  background: rgba(255,255,255,.2); padding: 3px 10px;
  font-size: 12px; border-radius: 4px;
}
.resolve-btn:hover { background: rgba(255,255,255,.35); }
</style>
