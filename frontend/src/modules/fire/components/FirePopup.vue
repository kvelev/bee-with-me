<template>
  <section class="fire-popup" role="dialog" :aria-label="title">
    <header class="fp-head">
      <h3 class="fp-title">{{ title }}</h3>
      <button type="button" class="fp-close" :aria-label="t('fire.close')" @click="emit('close')">&times;</button>
    </header>

    <dl v-if="kind === 'hotspot'" class="fp-rows">
      <div class="fp-row">
        <dt>{{ t('fire.popup.detected') }}</dt>
        <dd>
          <span class="fp-mono">{{ relative(properties.acquired_at) }}</span>
          <span v-if="utc(properties.acquired_at)" class="fp-sub fp-mono">{{ utc(properties.acquired_at) }}</span>
        </dd>
      </div>
      <div class="fp-row">
        <dt>{{ t('fire.popup.source') }}</dt>
        <dd>{{ sourceLabel }}</dd>
      </div>
      <div v-if="properties.state && properties.state !== 'active'" class="fp-row">
        <dt>{{ t('fire.popup.state') }}</dt>
        <dd><span class="fp-chip">{{ stateLabel }}</span></dd>
      </div>
      <div v-if="properties.notes" class="fp-row fp-notes">
        <dt>{{ t('fire.popup.notes') }}</dt>
        <dd>{{ properties.notes }}</dd>
      </div>
      <div v-if="properties.dismiss_notes" class="fp-row fp-notes">
        <dt>{{ t('fire.popup.dismissNotes') }}</dt>
        <dd>{{ properties.dismiss_notes }}</dd>
      </div>
    </dl>

    <dl v-else class="fp-rows">
      <div class="fp-row">
        <dt>{{ t('fire.popup.area') }}</dt>
        <dd><span class="fp-mono">{{ areaLabel }}</span></dd>
      </div>
      <div class="fp-row">
        <dt>{{ t('fire.popup.started') }}</dt>
        <dd><span class="fp-mono">{{ day(properties.started_at) }}</span></dd>
      </div>
      <div class="fp-row">
        <dt>{{ t('fire.popup.ended') }}</dt>
        <dd>
          <span class="fp-mono">{{ day(properties.ended_at) }}</span>
          <span v-if="burnedAgo" class="fp-sub">{{ burnedAgo }}</span>
        </dd>
      </div>
      <div v-if="properties.effis_fire_id" class="fp-row">
        <dt>{{ t('fire.popup.fireId') }}</dt>
        <dd><span class="fp-mono">{{ properties.effis_fire_id }}</span></dd>
      </div>
    </dl>

    <dl v-if="coords" class="fp-rows fp-coords">
      <div v-for="row in coordRows" :key="row.id" class="fp-row">
        <dt>{{ row.label }}</dt>
        <dd class="fp-copy">
          <span class="fp-mono fp-value" :data-testid="`fp-${row.id}`">{{ row.text }}</span>
          <button type="button" class="fp-copy-btn" :data-testid="`fp-copy-${row.id}`"
                  :aria-label="`${t('fire.popup.copy')}: ${row.label}`" @click="copy(row)">
            {{ copiedId === row.id ? (copyOk ? t('fire.popup.copied') : t('fire.popup.copyFailed')) : t('fire.popup.copy') }}
          </button>
        </dd>
      </div>
    </dl>
    <p class="fp-live" role="status" aria-live="polite" data-testid="fp-copy-status">{{ liveMsg }}</p>

    <div v-if="kind === 'hotspot' && (canDismiss || canCreateZone || canExtinguish)" class="fp-actions">
      <div v-if="canDismiss && noteOpen" class="fp-note-field">
        <label :for="noteId">{{ t('fire.popup.noteLabel') }}</label>
        <textarea :id="noteId" v-model="note" rows="3" :maxlength="NOTES_MAX" data-testid="fp-note" />
        <span class="fp-count fp-mono" :class="{ 'fp-count-near': note.length > NOTES_MAX - 100 }">{{ note.length }}/{{ NOTES_MAX }}</span>
      </div>
      <div class="fp-buttons">
        <button v-if="canDismiss" type="button" class="fp-btn" data-action="dismiss" :disabled="busy" @click="onDismiss">
          {{ t('fire.popup.dismiss') }}
        </button>
        <button v-if="canCreateZone" type="button" class="fp-btn" data-action="create-zone" :disabled="busy" @click="onCreateZone">
          {{ t('fire.popup.createZone') }}
        </button>
        <button v-if="canExtinguish" type="button" class="fp-btn" data-action="extinguish" :disabled="busy" @click="emit('extinguish', { id: properties.id })">
          {{ t('fire.popup.extinguish') }}
        </button>
      </div>
      <button v-if="canDismiss" type="button" class="fp-link" data-action="toggle-note" :aria-expanded="noteOpen" @click="noteOpen = !noteOpen">
        {{ noteOpen ? t('fire.popup.noNote') : t('fire.popup.addNote') }}
      </button>
      <p v-if="errorText" class="fp-error" role="alert" data-testid="fp-error">{{ errorText }}</p>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { forward as toMGRS } from 'mgrs'

// Every property is rendered as text through Vue interpolation; field-report notes and
// dismiss notes are user text and must never reach innerHTML. Dismiss and Create zone are
// admin actions; Extinguish is open to every signed-in user, for field reports only. The
// popup only emits: MapView calls the store and passes `busy` and `errorText` back.
const props = defineProps({
  kind:       { type: String, required: true, validator: v => v === 'hotspot' || v === 'burnt_area' },
  properties: { type: Object, required: true },
  isAdmin:    { type: Boolean, default: false },
  // WGS84 [lon, lat] in degrees (the map hands over EPSG:3857; MapView converts).
  lonLat:     { type: Array, default: null },
  busy:       { type: Boolean, default: false },
  errorText:  { type: String, default: '' },
})
const emit = defineEmits(['close', 'dismiss', 'create-zone', 'extinguish'])

const { t } = useI18n()

const NOTES_MAX = 1000
const noteId = `fp-note-${Math.random().toString(36).slice(2, 8)}`
const noteOpen = ref(false)
const note = ref('')

const canDismiss    = computed(() => props.isAdmin && props.properties.state !== 'dismissed')
const canCreateZone = computed(() => props.isAdmin)
const canExtinguish = computed(() => props.properties.source === 'field_report' && props.properties.state !== 'extinguished')

// A new selection or a changed state starts with a closed, empty note.
watch(() => [props.properties.id, props.properties.state], () => { noteOpen.value = false; note.value = '' })

function onDismiss() {
  const text = note.value.trim()
  emit('dismiss', { id: props.properties.id, notes: text || null })
}

function onCreateZone() {
  emit('create-zone', { latitude: coords.value?.lat ?? null, longitude: coords.value?.lon ?? null })
}

const MIN = 60_000, HOUR = 3_600_000, DAY = 86_400_000

const title = computed(() => t(props.kind === 'hotspot' ? 'fire.popup.hotspotTitle' : 'fire.popup.burntTitle'))

const sourceLabel = computed(() => {
  const s = props.properties.source
  return ['viirs', 'modis', 'field_report'].includes(s) ? t(`fire.source.${s}`) : (s ?? t('fire.unknown'))
})

const STATES = ['active', 'dismissed', 'extinguished', 'suppressed']
const stateLabel = computed(() => {
  const s = props.properties.state
  return STATES.includes(s) ? t(`fire.state.${s}`) : t('fire.unknown')
})

// null, undefined and '' are "not reported", not zero and not the epoch: Number(null) is 0
// and new Date(null) is 1970, so check before converting (BP-01, BP-03).
const isBlank = v => v === null || v === undefined || v === ''

const areaLabel = computed(() => {
  if (isBlank(props.properties.area_ha)) return t('fire.unknown')
  const a = Number(props.properties.area_ha)
  return Number.isFinite(a) ? `${a.toLocaleString(undefined, { maximumFractionDigits: 1 })} ${t('fire.popup.ha')}` : t('fire.unknown')
})

function ageMsOf(iso) {
  if (isBlank(iso)) return null
  const ms = Date.now() - Date.parse(iso)
  return Number.isFinite(ms) ? Math.max(0, ms) : null
}

function relative(iso) {
  const ms = ageMsOf(iso)
  if (ms == null) return t('fire.unknown')
  if (ms < MIN)  return t('fire.ago.now')
  if (ms < HOUR) return t('fire.ago.minutes', { n: Math.floor(ms / MIN) })
  if (ms < DAY)  return t('fire.ago.hours', { n: Math.floor(ms / HOUR) })
  return t('fire.ago.days', { n: Math.floor(ms / DAY) })
}

function utc(iso) {
  if (isBlank(iso)) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : `${d.toISOString().slice(0, 16).replace('T', ' ')} UTC`
}

function day(iso) {
  if (isBlank(iso)) return t('fire.unknown')
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? t('fire.unknown') : d.toISOString().slice(0, 10)
}

const burnedAgo = computed(() => {
  const ms = ageMsOf(props.properties.ended_at ?? props.properties.started_at)
  if (ms == null) return ''
  return t('fire.popup.burnedDaysAgo', { n: Math.floor(ms / DAY) })
})

// Coordinates: decimal degrees, `lat, lon`, 5 decimals, always a decimal point (toFixed is
// locale-free) so the text pastes into other tools whatever the UI language.
const coords = computed(() => {
  const ll = props.lonLat
  if (!Array.isArray(ll) || ll.length < 2) return null
  const lon = Number(ll[0]), lat = Number(ll[1])
  if (!Number.isFinite(lon) || !Number.isFinite(lat) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return null
  return { lat, lon }
})

const mgrsText = computed(() => {
  if (!coords.value) return ''
  try { return toMGRS([coords.value.lon, coords.value.lat], 5) } catch { return '' }
})

const coordRows = computed(() => {
  const c = coords.value
  if (!c) return []
  const rows = [{
    id: 'latlon',
    label: t(props.kind === 'hotspot' ? 'fire.popup.coordinates' : 'fire.popup.clickedPoint'),
    text: `${c.lat.toFixed(5)}, ${c.lon.toFixed(5)}`,
  }]
  if (mgrsText.value) rows.push({ id: 'mgrs', label: t('fire.popup.mgrs'), text: mgrsText.value })
  return rows
})

const copiedId = ref('')
const copyOk = ref(false)
const liveMsg = ref('')
let feedbackTimer = null

// navigator.clipboard exists only in secure contexts (https or localhost); the field laptop
// may be reached over plain http on the intranet, so fall back to execCommand.
async function writeClipboard(text) {
  if (navigator.clipboard?.writeText) {
    try { await navigator.clipboard.writeText(text); return true } catch { /* try the fallback */ }
  }
  const ta = document.createElement('textarea')
  ta.value = text
  ta.setAttribute('readonly', '')
  ta.setAttribute('aria-hidden', 'true')
  ta.style.cssText = 'position:fixed;top:0;left:0;opacity:0;pointer-events:none'
  document.body.appendChild(ta)
  ta.select()
  ta.setSelectionRange(0, text.length)
  let ok = false
  try { ok = document.execCommand('copy') } catch { ok = false }
  ta.remove()
  return ok
}

async function copy(row) {
  const ok = await writeClipboard(row.text)
  copiedId.value = row.id
  copyOk.value = ok
  liveMsg.value = t(ok ? 'fire.popup.copied' : 'fire.popup.copyFailed')
  clearTimeout(feedbackTimer)
  feedbackTimer = setTimeout(() => { copiedId.value = ''; liveMsg.value = '' }, 2500)
}

function onKey(e) { if (e.key === 'Escape') emit('close') }
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => { window.removeEventListener('keydown', onKey); clearTimeout(feedbackTimer) })
</script>

<style scoped>
.fire-popup {
  position: relative;
  width: 260px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 4px 18px rgba(0, 0, 0, .55);
  color: var(--text);
  font-size: 13px;
}
.fp-head {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 10px 12px; border-bottom: 1px solid var(--border);
}
.fp-title { font-size: 13px; font-weight: 700; }
.fp-close {
  background: transparent; color: var(--text-muted);
  padding: 0 6px; font-size: 20px; line-height: 1; border-radius: 4px;
}
.fp-close:hover { color: var(--text); opacity: 1; }
.fp-close:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }

.fp-rows { padding: 6px 12px 10px; }
.fp-row { display: grid; grid-template-columns: 78px 1fr; gap: 8px; padding: 5px 0; }
.fp-row dt { color: var(--text-muted); font-size: 12px; }
.fp-row dd { min-width: 0; overflow-wrap: anywhere; }
.fp-mono { font-family: monospace; font-variant-numeric: tabular-nums; font-weight: 600; }
.fp-sub { display: block; color: var(--text-muted); font-size: 11px; font-weight: 400; }
.fp-chip {
  display: inline-block; padding: 1px 8px; border-radius: 99px;
  border: 1px solid var(--border); background: var(--bg-card);
  color: var(--text-muted); font-size: 11px; font-weight: 600;
}
.fp-coords { border-top: 1px solid var(--border); }
.fp-copy { display: flex; align-items: center; justify-content: space-between; gap: 6px; flex-wrap: wrap; }
.fp-value { overflow-wrap: anywhere; user-select: all; }
.fp-copy-btn {
  background: transparent; color: var(--accent); border: 1px solid var(--accent);
  border-radius: 6px; padding: 3px 10px; min-height: 28px; font-size: 12px; font-weight: 600;
  white-space: nowrap;
}
.fp-copy-btn:hover { background: var(--bg-card); opacity: 1; }
.fp-copy-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.fp-live { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
.fp-notes dd { white-space: pre-wrap; max-height: 96px; overflow-y: auto; }

/* Actions: plain secondary buttons. Dismiss is not destructive and Create zone is reversible,
   so nothing here is red (red is for alarms and data loss). */
.fp-actions { border-top: 1px solid var(--border); padding: 10px 12px 12px; display: flex; flex-direction: column; gap: 8px; }
.fp-buttons { display: flex; flex-wrap: wrap; gap: 6px; }
.fp-btn {
  background: var(--bg-card); border: 1px solid var(--border); color: var(--text);
  padding: 6px 12px; min-height: 34px; font-size: 13px; font-weight: 600; border-radius: 6px;
}
.fp-btn:focus-visible, .fp-link:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.fp-btn:disabled { opacity: .45; cursor: not-allowed; }
.fp-link {
  align-self: flex-start; background: transparent; color: var(--accent);
  padding: 2px 0; font-size: 12px; font-weight: 600; text-decoration: underline; text-underline-offset: 2px;
}
.fp-note-field label { font-size: 12px; margin-bottom: 4px; }
.fp-note-field textarea {
  width: 100%; resize: vertical; min-height: 64px; max-height: 140px; font: inherit; font-size: 13px; padding: 6px 8px;
}
.fp-note-field textarea:focus { border-color: var(--accent); }
.fp-count { display: block; text-align: right; font-size: 11px; color: var(--text-muted); font-weight: 400; margin-top: 2px; }
.fp-count-near { color: var(--warning); }
.fp-error { font-size: 12px; color: var(--warning); line-height: 1.4; }
@media (hover: hover) and (pointer: fine) {
  .fp-btn:hover:not(:disabled) { border-color: var(--accent); opacity: 1; }
  .fp-link:hover { color: var(--text); }
}
</style>
