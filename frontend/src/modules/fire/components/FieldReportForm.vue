<template>
  <form class="map-dialog" role="dialog" :aria-labelledby="titleId" data-testid="field-report-form"
        @submit.prevent="onSubmit" @keydown.esc.stop="emit('cancel')">
    <h3 :id="titleId" class="md-title">{{ t('fire.report.title') }}</h3>

    <dl class="md-facts">
      <div v-if="target.name" class="md-fact">
        <dt>{{ t('fire.report.rescuer') }}</dt>
        <dd data-testid="fr-rescuer">{{ target.name }}</dd>
      </div>
      <div v-if="latLonText" class="md-fact">
        <dt>{{ target.name ? t('fire.report.position') : t('fire.report.point') }}</dt>
        <dd>
          <span class="md-mono" data-testid="fr-latlon">{{ latLonText }}</span>
          <span v-if="timeText" class="md-sub" data-testid="fr-time">{{ t('fire.report.positionAt', { time: timeText }) }}</span>
        </dd>
      </div>
      <div v-if="mgrsText" class="md-fact">
        <dt>{{ t('fire.popup.mgrs') }}</dt>
        <dd><span class="md-mono" data-testid="fr-mgrs">{{ mgrsText }}</span></dd>
      </div>
    </dl>
    <p v-if="!target.noPosition && target.gnssValid === false" class="md-warn" role="status" data-testid="fr-nofix">{{ t('fire.report.noFix') }}</p>
    <p v-if="!target.noPosition" class="md-hint">{{ target.name ? t('fire.report.hintDevice') : t('fire.report.hintPoint') }}</p>

    <div class="md-field">
      <label :for="notesId">{{ t('fire.report.notes') }}</label>
      <textarea :id="notesId" v-model="notes" rows="3" :maxlength="NOTES_MAX" data-testid="fr-notes" />
      <span class="md-count md-mono" :class="{ 'md-count-near': notes.length > NOTES_MAX - 100 }">{{ notes.length }}/{{ NOTES_MAX }}</span>
    </div>

    <p v-if="shownError" class="md-error" role="alert" data-testid="fr-error">{{ shownError }}</p>

    <div class="md-actions">
      <button ref="submitEl" type="submit" :disabled="busy || !!target.noPosition" data-testid="fr-submit">
        {{ busy ? t('fire.report.sending') : t('fire.report.submit') }}
      </button>
      <button type="button" class="secondary" :disabled="busy" data-testid="fr-cancel" @click="emit('cancel')">
        {{ t('common.cancel') }}
      </button>
    </div>
  </form>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { forward as toMGRS } from 'mgrs'

// Asks only for the optional note; MapView owns the request and passes the outcome back through
// `busy` and `errorText`. `target` is a point frozen when the form opened: { latitude, longitude }, plus
// { name, mgrs, receivedAt, gnssValid } for a volunteer (gnssValid false: the position is the last known one, shown in amber, submit stays allowed), or { name, noPosition: true } when none is usable. Notes are free
// operator text: rendered by the browser as a textarea value, never as markup, never logged.
const props = defineProps({
  target:    { type: Object, required: true },
  busy:      { type: Boolean, default: false },
  errorText: { type: String, default: '' },
})
const emit = defineEmits(['submit', 'cancel'])

const { t } = useI18n()
const NOTES_MAX = 1000
const uid = Math.random().toString(36).slice(2, 8)
const titleId = `fr-title-${uid}`
const notesId = `fr-notes-${uid}`
const notes = ref('')
const submitEl = ref(null)

const point = computed(() => {
  const lat = Number(props.target.latitude), lon = Number(props.target.longitude)
  return Number.isFinite(lat) && Number.isFinite(lon) ? { lat, lon } : null
})
const latLonText = computed(() => (point.value ? `${point.value.lat.toFixed(5)}, ${point.value.lon.toFixed(5)}` : ''))
const timeText = computed(() => {
  const ms = Number(props.target.receivedAt)
  return props.target.receivedAt != null && Number.isFinite(ms)
    ? new Date(ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''
})
// A rescuer without a recent position cannot be reported: say so here, never call the API.
const shownError = computed(() => (props.target.noPosition ? t('fire.errors.noRecentPosition') : props.errorText))
const mgrsText = computed(() => {
  if (props.target.mgrs) return props.target.mgrs
  if (!point.value) return ''
  try { return toMGRS([point.value.lon, point.value.lat], 5) } catch { return '' }
})

function onSubmit() {
  if (props.busy || props.target.noPosition) return
  const text = notes.value.trim()
  emit('submit', { notes: text || null })
}

// Focus lands on the submit button: Enter files the report, Escape cancels, the note is optional.
onMounted(() => submitEl.value?.focus())
</script>
