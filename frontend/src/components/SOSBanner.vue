<template>
  <div v-if="store.hasSOS" class="sos-banner sos-pulse">
    <span>{{ t('sos.active') }}</span>
    <span v-for="alert in store.sosAlerts" :key="alert.id ?? alert.device_id" class="sos-entry">
      {{ alert.full_name || 'Unknown' }} ({{ alert.dev_sn ?? '—' }})
      <button class="resolve-btn" :disabled="busy === alert.id" @click="resolve(alert)">
        {{ busy === alert.id ? t('sos.resolving') : t('sos.resolve') }}
      </button>
    </span>
    <span v-if="error" class="sos-error">{{ error }}</span>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useLocationsStore } from '../stores/locations'

const { t } = useI18n()
const store = useLocationsStore()
const busy  = ref(null)
const error = ref('')

async function resolve(alert) {
  error.value = ''
  busy.value  = alert.id
  try {
    await store.resolveSOS(alert.id)
  } catch (e) {
    // Previously this rejection was swallowed and the alert simply stayed on screen, which
    // read as "the Resolve button does nothing". Say what went wrong instead.
    error.value = typeof e === 'string' ? e : (e?.message ?? t('sos.resolveFailed'))
  } finally {
    busy.value = null
  }
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
.resolve-btn:disabled { opacity: .55; cursor: default; }
.sos-error {
  font-weight: 400;
  font-size: 12.5px;
  background: rgba(0,0,0,.28);
  padding: 3px 10px;
  border-radius: 4px;
}
</style>
