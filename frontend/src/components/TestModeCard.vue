<template>
  <!-- Renders only when the server has test endpoints enabled (GET /test/simulation answers). -->
  <section v-if="status" class="card test-mode" aria-labelledby="test-mode-title" data-testid="test-mode">
    <h3 id="test-mode-title" class="section-title">{{ t('settings.testMode.title') }}</h3>
    <p class="warn">{{ t('settings.testMode.warning') }}</p>

    <p v-if="status.running" class="state on" data-testid="test-mode-state" role="status">
      {{ t('settings.testMode.running', { devices: status.devices, steps: status.steps, interval: status.interval }) }}
    </p>
    <p v-else class="state" data-testid="test-mode-state" role="status">{{ t('settings.testMode.stopped') }}</p>
    <p v-if="status.last_error" class="error">{{ t('settings.testMode.stepFailed', { error: status.last_error }) }}</p>

    <div v-if="!status.running" class="fields">
      <div class="field">
        <label for="tm-lat">{{ t('settings.testMode.lat') }}</label>
        <input id="tm-lat" v-model.number="form.lat" type="number" step="0.001" min="-90" max="90" />
      </div>
      <div class="field">
        <label for="tm-lon">{{ t('settings.testMode.lon') }}</label>
        <input id="tm-lon" v-model.number="form.lon" type="number" step="0.001" min="-180" max="180" />
      </div>
      <div class="field">
        <label for="tm-interval">{{ t('settings.testMode.interval') }}</label>
        <input id="tm-interval" v-model.number="form.interval" type="number" step="1" min="1" max="60" />
      </div>
    </div>

    <div class="row">
      <button v-if="status.running" type="button" class="danger" data-testid="test-mode-stop" :disabled="busy" @click="onStop">
        {{ t('settings.testMode.stop') }}
      </button>
      <button v-else type="button" data-testid="test-mode-start" :disabled="busy" @click="onStart">
        {{ t('settings.testMode.start') }}
      </button>
      <span v-if="failed" class="error" role="alert">{{ failed }}</span>
    </div>
    <p class="hint">{{ t('settings.testMode.hint') }}</p>
  </section>
</template>

<script setup>
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { getSimulation, startSimulation, stopSimulation } from '../api'
import { detailOf } from '../api/client'

const { t } = useI18n()

const POLL_MS = 5000
const status = ref(null)          // null = test mode not available on this server: render nothing
const form = reactive({ lat: 42.698, lon: 23.322, interval: 3 })   // Sofia, like tools/demo.py
const busy = ref(false)
const failed = ref('')
let timer = null

async function refresh() {
  try {
    const data = await getSimulation()   // the API client already unwraps response.data
    status.value = data
    if (!data.running) Object.assign(form, { lat: data.lat || form.lat, lon: data.lon || form.lon, interval: data.interval || form.interval })
  } catch {
    // 404 (test endpoints off), 403, network: the card stays hidden / keeps its last state
    if (status.value === null) stopPolling()
  }
}

async function onStart() {
  busy.value = true
  failed.value = ''
  try {
    status.value = await startSimulation({ lat: form.lat, lon: form.lon, interval: form.interval })
  } catch (e) {
    failed.value = messageOf(e, 'settings.testMode.startFailed')
  } finally {
    busy.value = false
  }
}

async function onStop() {
  busy.value = true
  failed.value = ''
  try {
    status.value = await stopSimulation()
  } catch (e) {
    failed.value = messageOf(e, 'settings.testMode.stopFailed')
  } finally {
    busy.value = false
  }
}

// A 422 detail is a list of field errors, not a sentence: fall back to our own message then
function messageOf(e, fallbackKey) {
  const detail = detailOf(e)
  return typeof detail === 'string' && detail ? detail : t(fallbackKey)
}

function stopPolling() {
  clearInterval(timer)
  timer = null
}

onMounted(async () => {
  await refresh()
  if (status.value) timer = setInterval(refresh, POLL_MS)
})
onUnmounted(stopPolling)
</script>

<style scoped>
.test-mode { margin-top: 16px; border-color: var(--warning-line); }
.section-title { font-size: 14px; font-weight: 600; margin-bottom: 12px; color: var(--text-muted); }
.warn { font-size: 13px; color: var(--warning); background: var(--warning-wash); border: 1px solid var(--warning-line); border-radius: 6px; padding: 8px 10px; margin-bottom: 12px; }
.state { font-size: 14px; margin-bottom: 12px; }
.state.on { color: var(--success); font-weight: 600; }
.fields { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.field { width: 140px; }
.field input { font-family: ui-monospace, monospace; }
.row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.error { font-size: 13px; color: var(--danger); }
.hint { font-size: 13px; color: var(--text-muted); margin-top: 10px; margin-bottom: 0; }
</style>
