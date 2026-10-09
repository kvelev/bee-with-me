<template>
  <!-- Renders only when the server has test endpoints enabled (GET /test/simulation answers). -->
  <section v-if="status" class="card test-mode" aria-labelledby="test-mode-title" data-testid="test-mode">
    <h3 id="test-mode-title" class="section-title">{{ t('settings.testMode.title') }}</h3>
    <p class="warn">{{ t('settings.testMode.warning') }}</p>

    <p v-if="status.running" class="state on" data-testid="test-mode-state" role="status">
      {{ t('settings.testMode.running', { devices: status.devices, steps: status.steps, interval: status.interval }) }}
      <span v-if="status.scenario" class="scenario" data-testid="test-mode-scenario">{{ scenarioSummary(status.scenario) }}</span>
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

    <template v-if="!status.running">
      <h4 class="sub-title">{{ t('settings.testMode.scenario') }}</h4>
      <div class="fields">
        <div v-for="f in COUNT_FIELDS" :key="f.key" class="field">
          <label :for="'tm-' + f.key">{{ t('settings.testMode.' + f.key) }}</label>
          <input :id="'tm-' + f.key" v-model.number="form[f.key]" type="number" step="1" :min="f.min" :max="f.max" />
        </div>
        <div class="field">
          <label for="tm-step_m">{{ t('settings.testMode.step_m') }}</label>
          <input id="tm-step_m" v-model.number="form.step_m" type="number" step="5" min="5" max="2000" />
        </div>
        <div class="field">
          <label for="tm-spread_km">{{ t('settings.testMode.spread_km') }}</label>
          <input id="tm-spread_km" v-model.number="form.spread_km" type="number" step="0.5" min="0.5" max="50" />
        </div>
      </div>
      <p class="hint flush">{{ t('settings.testMode.scenarioHint') }}</p>
      <p v-if="scenarioError" class="error" role="alert" data-testid="test-mode-scenario-error">{{ scenarioError }}</p>
    </template>

    <div class="row">
      <button v-if="status.running" type="button" class="danger" data-testid="test-mode-stop" :disabled="busy" @click="onStop">
        {{ t('settings.testMode.stop') }}
      </button>
      <button v-else type="button" data-testid="test-mode-start" :disabled="busy || !!scenarioError" @click="onStart">
        {{ t('settings.testMode.start') }}
      </button>
      <button type="button" class="secondary" data-testid="test-mode-reset" :disabled="busy" @click="onReset">
        {{ t('settings.testMode.reset') }}
      </button>
      <span v-if="resetDone" class="ok" role="status">{{ resetDone }}</span>
      <span v-if="failed" class="error" role="alert">{{ failed }}</span>
    </div>
    <p class="hint">{{ t('settings.testMode.hint') }}</p>
  </section>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { getSimulation, resetSimulation, startSimulation, stopSimulation } from '../api'
import { detailOf } from '../api/client'

const { t } = useI18n()

const POLL_MS = 5000
const status = ref(null)          // null = test mode not available on this server: render nothing
const form = reactive({
  lat: 42.698, lon: 23.322, interval: 3,   // Sofia, like tools/demo.py
  // scenario (backend/simulation.Scenario): defaults = six personas, one in SOS
  trackers: 6, sos: 1, no_fix: 0, stale: 0, lost: 0, low_battery: 0, step_m: 300, spread_km: 5,
})
const COUNT_FIELDS = [
  { key: 'trackers', min: 1, max: 12 },
  { key: 'sos', min: 0, max: 12 },
  { key: 'no_fix', min: 0, max: 12 },
  { key: 'stale', min: 0, max: 12 },
  { key: 'lost', min: 0, max: 12 },
  { key: 'low_battery', min: 0, max: 12 },
]
const SCENARIO_KEYS = ['trackers', 'sos', 'no_fix', 'stale', 'lost', 'low_battery', 'step_m', 'spread_km']
const busy = ref(false)
const failed = ref('')
const resetDone = ref('')

// Same rule as the server (routers/test.SimulationStart), checked before the request is sent
const scenarioError = computed(() => {
  const n = (k) => Number(form[k]) || 0
  if (n('sos') + n('no_fix') + n('stale') + n('lost') > n('trackers')) return t('settings.testMode.tooManyStates')
  if (n('low_battery') > n('trackers')) return t('settings.testMode.tooManyLowBattery')
  return ''
})

function scenarioSummary(s) {
  return t('settings.testMode.summary', s)
}
let timer = null

async function refresh() {
  try {
    const data = await getSimulation()   // the API client already unwraps response.data
    status.value = data
    if (!data.running) {
      Object.assign(form, { lat: data.lat || form.lat, lon: data.lon || form.lon, interval: data.interval || form.interval })
      if (data.started_at && data.scenario) Object.assign(form, data.scenario)   // last run's scenario
    }
  } catch {
    // 404 (test endpoints off), 403, network: the card stays hidden / keeps its last state
    if (status.value === null) stopPolling()
  }
}

async function onStart() {
  busy.value = true
  failed.value = ''
  try {
    const body = { lat: form.lat, lon: form.lon, interval: form.interval }
    for (const k of SCENARIO_KEYS) body[k] = form[k]
    status.value = await startSimulation(body)
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

async function onReset() {
  busy.value = true
  failed.value = ''
  resetDone.value = ''
  try {
    const data = await resetSimulation()
    status.value = data
    resetDone.value = t('settings.testMode.resetDone', data.deleted ?? { positions: 0, sos_alerts: 0 })
  } catch (e) {
    failed.value = messageOf(e, 'settings.testMode.resetFailed')
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
.ok { font-size: 13px; color: var(--success); }
.sub-title { font-size: 13px; font-weight: 600; color: var(--text-muted); margin: 4px 0 8px; }
.scenario { display: block; font-weight: 400; color: var(--text-muted); font-size: 13px; margin-top: 2px; }
.hint.flush { margin-top: 0; margin-bottom: 12px; }
.hint { font-size: 13px; color: var(--text-muted); margin-top: 10px; margin-bottom: 0; }
</style>
