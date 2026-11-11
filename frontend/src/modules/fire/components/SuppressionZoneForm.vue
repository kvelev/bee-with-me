<template>
  <form :class="inline ? 'zone-inline' : 'map-dialog'" role="group" :aria-labelledby="titleId" novalidate
        data-testid="zone-form" @submit.prevent="onSubmit" @keydown.esc.stop="emit('cancel')">
    <h3 :id="titleId" class="md-title">{{ mode === 'edit' ? t('fire.zone.editTitle') : t('fire.zone.createTitle') }}</h3>

    <p class="md-hint">{{ t('fire.zone.hint') }}</p>

    <div class="md-field">
      <label :for="labelId">{{ t('fire.zone.label') }}</label>
      <input :id="labelId" ref="labelEl" v-model="label" type="text" maxlength="255" autocomplete="off"
             :aria-invalid="!!shown.label" :aria-describedby="`${labelId}-err`" data-testid="zone-label" />
      <p :id="`${labelId}-err`" class="md-field-error">{{ shown.label ? t(shown.label) : '' }}</p>
    </div>

    <div class="md-field md-radius">
      <label :for="radiusId">{{ t('fire.zone.radius') }}</label>
      <div class="md-with-unit">
        <input :id="radiusId" v-model="radius" type="number" inputmode="numeric" step="50" min="50" max="20000"
               :aria-invalid="!!shown.radius" :aria-describedby="`${radiusId}-err`" data-testid="zone-radius" />
        <span class="md-unit">{{ t('fire.zone.unitM') }}</span>
      </div>
      <p :id="`${radiusId}-err`" class="md-field-error">{{ shown.radius ? t(shown.radius) : '' }}</p>
    </div>

    <div class="md-field">
      <label :for="notesId">{{ t('fire.zone.notes') }}</label>
      <textarea :id="notesId" v-model="notes" rows="2" :maxlength="NOTES_MAX" data-testid="zone-notes" />
    </div>

    <div v-if="pointText" class="md-fact md-point">
      <span class="md-fact-label">{{ t('fire.zone.centre') }}</span>
      <span class="md-mono" data-testid="zone-point">{{ pointText }}</span>
    </div>

    <p v-if="errorText" class="md-error" role="alert" data-testid="zone-error">{{ errorText }}</p>

    <div class="md-actions">
      <button type="submit" :disabled="busy || locked" data-testid="zone-submit">
        {{ busy ? t('fire.zone.saving') : (mode === 'edit' ? t('fire.zone.save') : t('fire.zone.create')) }}
      </button>
      <button type="button" class="secondary" :disabled="busy" data-testid="zone-cancel" @click="emit('cancel')">
        {{ t('common.cancel') }}
      </button>
    </div>
  </form>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

// Create (from a hotspot popup) and edit (Settings) share this form. It validates what the
// server validates (label 1 to 255 characters, radius a whole number from 50 to 20000 m) and
// emits the cleaned values; the caller sends them and passes `busy` / `errorText` back. The
// centre is fixed: to move a zone, disable it and create a new one.
const props = defineProps({
  mode:      { type: String, default: 'create', validator: v => v === 'create' || v === 'edit' },
  initial:   { type: Object, default: () => ({}) },
  latitude:  { type: Number, default: null },
  longitude: { type: Number, default: null },
  inline:    { type: Boolean, default: false },
  busy:      { type: Boolean, default: false },   // a real save is in flight: submit says Saving, Cancel waits
  locked:    { type: Boolean, default: false },   // submit only: the values are out of date (Cancel stays usable)
  errorText: { type: String, default: '' },
})
const emit = defineEmits(['submit', 'cancel'])

const { t } = useI18n()
const NOTES_MAX = 1000
const RADIUS_MIN = 50, RADIUS_MAX = 20_000
const uid = Math.random().toString(36).slice(2, 8)
const titleId = `zf-title-${uid}`
const labelId = `zf-label-${uid}`
const radiusId = `zf-radius-${uid}`
const notesId = `zf-notes-${uid}`

const label = ref(props.initial.label ?? '')
const radius = ref(props.initial.radius_m ?? 1000)
const notes = ref(props.initial.notes ?? '')
const labelEl = ref(null)
const attempted = ref(false)

const errors = computed(() => {
  const r = Number(radius.value)
  return {
    label: label.value.trim() ? '' : 'fire.zone.errLabel',
    radius: radius.value !== '' && Number.isInteger(r) && r >= RADIUS_MIN && r <= RADIUS_MAX ? '' : 'fire.zone.errRadius',
  }
})
const shown = computed(() => (attempted.value ? errors.value : { label: '', radius: '' }))

const pointText = computed(() => {
  const lat = Number(props.latitude ?? props.initial.latitude)
  const lon = Number(props.longitude ?? props.initial.longitude)
  const has = (props.latitude ?? props.initial.latitude) != null && (props.longitude ?? props.initial.longitude) != null
  return has && Number.isFinite(lat) && Number.isFinite(lon) ? `${lat.toFixed(5)}, ${lon.toFixed(5)}` : ''
})

function onSubmit() {
  if (props.busy || props.locked) return
  attempted.value = true
  if (errors.value.label || errors.value.radius) return
  emit('submit', { label: label.value.trim(), radius_m: Number(radius.value), notes: notes.value.trim() || null })
}

onMounted(() => labelEl.value?.focus())
</script>

<style scoped>
.md-radius { max-width: 200px; }
.md-point { align-items: baseline; }
.zone-inline {
  display: flex; flex-direction: column; gap: 10px; padding: 14px 16px;
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; font-size: 13px;
}
</style>
