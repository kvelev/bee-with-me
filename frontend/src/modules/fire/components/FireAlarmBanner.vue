<template>
  <p v-if="fire.alertsFailed" class="fb-loadfail" role="status">{{ t('fireAlarm.loadFailed') }}</p>

  <section
    v-if="fire.alerts.length"
    :class="['fire-banner', { 'fire-banner-live': hasUnack }]"
    :role="hasUnack ? 'alert' : 'region'"
    :aria-label="t('fireAlarm.region')"
  >
    <template v-if="hasUnack">
      <div class="fb-stripe" aria-hidden="true"></div>

      <header class="fb-head">
        <svg class="fb-flame" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path d="M12.6 2c.5 3.3 5.4 5.6 5.4 10.6A6 6 0 0 1 6 12.8c0-2.3 1.1-3.8 2.3-5 .2 1.5.9 2.5 1.9 3C9.7 8 10.4 4.4 12.6 2z" />
        </svg>
        <h2 class="fb-title">{{ t('fireAlarm.title') }}</h2>
        <span class="fb-count" aria-hidden="true">{{ fire.unacknowledged.length }}</span>
        <span class="fb-spacer"></span>
        <button v-if="soundNeedsClick" type="button" class="fb-btn fb-sound" @click="unlock">
          {{ t('fireAlarm.soundBlocked') }}
        </button>
        <button
          v-if="fire.unacknowledged.length > 1"
          type="button" class="fb-btn fb-btn-main" :disabled="allBusy" @click="ackAll"
        >{{ allBusy ? t('fireAlarm.busy') : t('fireAlarm.acknowledgeAll') }}</button>
      </header>
    </template>

    <p v-if="soundUnsupportedNow" class="fb-note">{{ t('fireAlarm.soundUnsupported') }}</p>
    <p v-if="fire.alertsHidden > 0" class="fb-note fb-hidden" role="status">
      {{ t('fireAlarm.moreHidden', { n: fire.alertsHidden }, fire.alertsHidden) }}
    </p>
    <p v-if="ackError" class="fb-note fb-error" role="alert">{{ ackError }}</p>

    <!-- Unacknowledged alerts are never collapsible (BP-02). -->
    <ul v-if="unackRows.length" class="fb-list">
      <li v-for="a in unackRows" :key="a.id" class="fb-row">
        <div class="fb-who">
          <span class="fb-name">{{ targetName(a) }}</span>
          <span v-if="a.target_type !== 'hq' && a.rank" class="fb-rank">{{ a.rank }}</span>
        </div>
        <i18n-t keypath="fireAlarm.detail" tag="p" class="fb-detail">
          <template #distance><span class="fb-mono fb-distance">{{ distanceText(a.distance_m) }}</span></template>
          <template #age><span class="fb-mono">{{ ageText(a.hotspot.acquired_at) }}</span></template>
        </i18n-t>
        <div class="fb-actions">
          <button type="button" class="fb-btn" @click="showOnMap(a)">{{ t('fireAlarm.showOnMap') }}</button>
          <button
            type="button" class="fb-btn fb-btn-main" :disabled="busy.has(a.id)" @click="ack(a)"
          >{{ busy.has(a.id) ? t('fireAlarm.busy') : t('fireAlarm.acknowledge') }}</button>
        </div>
      </li>
    </ul>

    <!-- Acknowledged but still open: quiet slate, one compact row when collapsed. -->
    <div v-if="ackRows.length" class="fb-ackzone">
      <button
        type="button" class="fb-toggle"
        :aria-expanded="ackCollapsed ? 'false' : 'true'" aria-controls="fb-ack-list"
        @click="toggleAck"
      >
        <svg class="fb-flame fb-flame-sm" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path d="M12.6 2c.5 3.3 5.4 5.6 5.4 10.6A6 6 0 0 1 6 12.8c0-2.3 1.1-3.8 2.3-5 .2 1.5.9 2.5 1.9 3C9.7 8 10.4 4.4 12.6 2z" />
        </svg>
        <span class="fb-toggle-label">{{ t('fireAlarm.ackedCount', { n: ackRows.length }, ackRows.length) }}</span>
        <span class="fb-toggle-act">
          {{ ackCollapsed ? t('fireAlarm.ackedShow') : t('fireAlarm.ackedHide') }}
          <span :class="['fb-chev', { 'fb-chev-open': !ackCollapsed }]" aria-hidden="true"></span>
        </span>
      </button>
      <ul v-show="!ackCollapsed" id="fb-ack-list" class="fb-list fb-list-acked">
        <li v-for="a in ackRows" :key="a.id" class="fb-row fb-row-acked">
          <div class="fb-who">
            <span class="fb-name">{{ targetName(a) }}</span>
            <span v-if="a.target_type !== 'hq' && a.rank" class="fb-rank">{{ a.rank }}</span>
          </div>
          <i18n-t keypath="fireAlarm.detail" tag="p" class="fb-detail">
            <template #distance><span class="fb-mono fb-distance">{{ distanceText(a.distance_m) }}</span></template>
            <template #age><span class="fb-mono">{{ ageText(a.hotspot.acquired_at) }}</span></template>
          </i18n-t>
          <div class="fb-actions">
            <button type="button" class="fb-btn" @click="showOnMap(a)">{{ t('fireAlarm.showOnMap') }}</button>
            <span class="fb-acked">{{ t('fireAlarm.acknowledged') }}</span>
          </div>
        </li>
      </ul>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useFireStore } from '../store.js'
import { errorText } from '../../../api/client'
import {
  TONE_BLOCKED, TONE_RUNNING, TONE_UNSUPPORTED, playFireTone, toneState, unlockFireTone,
} from '../lib/fireTone.js'

const { t, locale } = useI18n()
const fire = useFireStore()
const router = useRouter()

const hasUnack = computed(() => fire.unacknowledged.length > 0)

// Nearest to people first inside each group. The two groups are rendered apart so the
// unacknowledged one can never be folded away.
const byDistance = (a, b) => a.distance_m - b.distance_m
const unackRows = computed(() => fire.alerts.filter(a => !a.acknowledged_at).sort(byDistance))
const ackRows = computed(() => fire.alerts.filter(a => a.acknowledged_at).sort(byDistance))

// The operator's choice for the acknowledged group, per browser. Collapsed unless they opened it;
// blocked or broken storage must not break the banner.
const ACK_COLLAPSED_KEY = 'bwm.fireAlarm.ackCollapsed'
function readCollapsed() {
  try { return localStorage.getItem(ACK_COLLAPSED_KEY) !== '0' } catch { return true }
}
const ackCollapsed = ref(readCollapsed())
function toggleAck() {
  ackCollapsed.value = !ackCollapsed.value
  try { localStorage.setItem(ACK_COLLAPSED_KEY, ackCollapsed.value ? '1' : '0') } catch { /* blocked: kept for this page only */ }
}

function targetName(a) {
  if (a.target_type === 'hq') return t('fireAlarm.hq')
  return a.full_name || t('fireAlarm.unknownRescuer')
}

// Distance in km with one decimal, in the UI language's decimal mark; monospace (Read-It-Aloud).
function distanceText(m) {
  const km = new Intl.NumberFormat(locale.value, { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(m / 1000)
  return `${km} ${t('fireAlarm.unitKm')}`
}

// Age of the hotspot (BP-01), re-evaluated on a clock so a silent screen still ages.
const now = ref(Date.now())
let clock = null
function ageText(iso) {
  const ms = Math.max(0, now.value - new Date(iso).getTime())
  if (Number.isNaN(ms)) return t('fire.unknown')
  const MIN = 60_000, HOUR = 60 * MIN, DAY = 24 * HOUR
  if (ms < MIN)  return t('fire.ago.now')
  if (ms < HOUR) return t('fire.ago.minutes', { n: Math.floor(ms / MIN) })
  if (ms < DAY)  return t('fire.ago.hours', { n: Math.floor(ms / HOUR) })
  return t('fire.ago.days', { n: Math.floor(ms / DAY) })
}

// ---- Acknowledge ------------------------------------------------------------------------------
const busy = reactive(new Set())
const allBusy = ref(false)
const ackError = ref('')

async function ack(a) {
  ackError.value = ''
  busy.add(a.id)
  try {
    await fire.acknowledge(a.id)
  } catch (e) {
    ackError.value = errorText(e, t('fireAlarm.ackFailed'))
  } finally {
    busy.delete(a.id)
  }
}

async function ackAll() {
  ackError.value = ''
  allBusy.value = true
  try {
    await fire.acknowledgeAll()
  } catch (e) {
    ackError.value = errorText(e, t('fireAlarm.ackFailed'))
  } finally {
    allBusy.value = false
  }
}

function showOnMap(a) {
  fire.requestFocus(a.hotspot.latitude, a.hotspot.longitude)
  router.push('/map')
}

// ---- Tone -------------------------------------------------------------------------------------
// One tone per ringToken step (the store raises it once per repeat message). Browsers keep audio
// suspended until a user gesture: that is shown, never swallowed. A ring that could not play is
// remembered and plays once at the first click, if something is still unacknowledged.
const tone = ref(TONE_RUNNING)
let missedRing = false

const soundNeedsClick = computed(() => hasUnack.value && tone.value === TONE_BLOCKED)
const soundUnsupportedNow = computed(() => hasUnack.value && tone.value === TONE_UNSUPPORTED)

function ring() {
  tone.value = playFireTone()
  if (tone.value !== TONE_RUNNING) missedRing = true
}

async function unlock() {
  tone.value = await unlockFireTone()
  if (tone.value === TONE_RUNNING) {
    removeGestureListeners()
    if (missedRing && hasUnack.value) tone.value = playFireTone()
    missedRing = false
  }
}

// Only a rise rings: the reset to 0 at logout must not play a tone.
watch(() => fire.ringToken, (now, before) => { if (now > before) ring() })
// Restored alarms never ring on load, but the next repeat must be audible: check the state as
// soon as something needs it.
watch(hasUnack, (on) => { if (on) tone.value = toneState(); else missedRing = false }, { immediate: true })

const gestureEvents = ['pointerdown', 'keydown']
function removeGestureListeners() {
  for (const ev of gestureEvents) window.removeEventListener(ev, onGesture, true)
}
function onGesture() { unlock() }

onMounted(() => {
  for (const ev of gestureEvents) window.addEventListener(ev, onGesture, true)
  clock = setInterval(() => { now.value = Date.now() }, 15_000)
})
onUnmounted(() => {
  removeGestureListeners()
  clearInterval(clock)
})
</script>

<style scoped>
.fb-loadfail {
  flex-shrink: 0; padding: 8px 20px; font-size: 13px; color: var(--text);
  background: var(--warning-wash); border-bottom: 1px solid var(--warning-line);
}

/* Fire near people: its own family (ember ground, orange edge, flame, two-note low wail), not
   the SOS red/white banner. Quiet (everything acknowledged) drops to the slate surfaces. */
.fire-banner {
  flex-shrink: 0; max-height: 42dvh; overflow-y: auto;
  background: var(--bg-panel); color: var(--text-muted);
  border-bottom: 1px solid var(--border);
}
.fire-banner-live {
  background: var(--fire-alarm-ground); color: var(--fire-alarm-text);
  border-bottom: 2px solid var(--fire-alarm);
  animation: fire-glow 1.8s ease-in-out infinite alternate;
}
@keyframes fire-glow {
  from { box-shadow: 0 2px 10px color-mix(in srgb, var(--fire-alarm) 30%, transparent); }
  to   { box-shadow: 0 4px 26px color-mix(in srgb, var(--fire-alarm) 70%, transparent); }
}

.fb-stripe { height: 6px; background: var(--border); }
.fire-banner-live .fb-stripe {
  background: repeating-linear-gradient(135deg, var(--fire-alarm) 0 10px, var(--fire-alarm-ground) 10px 20px);
}

.fb-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 10px 20px 4px; }
.fb-flame { width: 22px; height: 22px; flex-shrink: 0; fill: currentColor; color: var(--text-muted); }
.fire-banner-live .fb-flame { color: var(--fire-alarm); }
.fb-title {
  font-size: 14px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
}
.fire-banner-live .fb-title { color: var(--fire-alarm-text); }
.fb-count {
  min-width: 22px; padding: 1px 7px; border-radius: 99px; text-align: center;
  font-family: monospace; font-size: 12px; font-weight: 700;
  border: 1px solid var(--border);
}
.fire-banner-live .fb-count { border-color: var(--fire-alarm); color: var(--fire-alarm); }
.fb-spacer { flex: 1; }

.fb-btn {
  padding: 5px 12px; font-size: 13px; font-weight: 600; border-radius: 6px;
  background: transparent; color: var(--text); border: 1px solid var(--border);
}
.fire-banner-live .fb-btn { color: var(--fire-alarm-text); border-color: var(--fire-alarm); }
.fire-banner-live .fb-btn-main {
  background: var(--fire-alarm-text); color: var(--fire-alarm-ink); border-color: var(--fire-alarm-text);
}
.fb-btn-main { background: var(--bg-card); }
.fb-btn:disabled { opacity: .55; cursor: default; }
.fb-sound { border-style: dashed; }

.fb-note { margin: 4px 20px 0; font-size: 13px; }
.fb-hidden { font-weight: 600; }
.fb-error { color: var(--fire-alarm-text); background: rgba(0,0,0,.35); padding: 4px 10px; border-radius: 4px; width: fit-content; }

.fb-list { list-style: none; padding: 4px 0 8px; }
.fb-list-acked { padding-top: 0; }

/* Acknowledged zone: always the quiet slate, also inside a live banner (Glow Is An Alarm). */
.fb-ackzone { background: var(--bg-panel); color: var(--text-muted); }
.fire-banner-live .fb-ackzone { border-top: 1px solid var(--border); }
.fb-toggle {
  display: flex; align-items: center; gap: 10px; width: 100%; min-height: 40px; padding: 6px 20px;
  background: transparent; color: var(--text-muted); border: 0; text-align: left;
  font-size: 13px; font-weight: 600; cursor: pointer;
}
.fb-toggle:hover { color: var(--text); }
.fb-toggle:focus-visible { outline: 2px solid var(--accent); outline-offset: -3px; }
.fb-flame-sm { width: 16px; height: 16px; }
.fb-toggle-label { flex: 1; min-width: 0; }
.fb-toggle-act { display: inline-flex; align-items: center; gap: 8px; color: var(--accent); }
.fb-chev {
  width: 7px; height: 7px; border-right: 2px solid currentColor; border-bottom: 2px solid currentColor;
  transform: translateY(-2px) rotate(45deg);
}
.fb-chev-open { transform: translateY(2px) rotate(-135deg); }
.fb-ackzone .fb-btn, .fire-banner-live .fb-ackzone .fb-btn { color: var(--text); border-color: var(--border); }
.fb-row {
  display: grid; grid-template-columns: minmax(120px, 220px) 1fr auto; align-items: center;
  gap: 4px 16px; padding: 8px 20px;
}
.fb-row + .fb-row { border-top: 1px solid color-mix(in srgb, currentColor 18%, transparent); }
.fb-who { display: flex; align-items: baseline; gap: 8px; min-width: 0; }
.fb-name { font-size: 15px; font-weight: 700; overflow-wrap: anywhere; }
.fire-banner-live .fb-name { color: #fff; }
.fb-row-acked .fb-name { color: var(--text-muted); font-weight: 600; }
.fb-rank { font-size: 12px; opacity: .8; }
.fb-detail { font-size: 13px; line-height: 1.4; }
.fb-mono { font-family: monospace; font-variant-numeric: tabular-nums; font-weight: 600; }
.fb-distance { font-size: 15px; }
.fb-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.fb-acked { font-size: 12px; font-weight: 600; color: var(--text-muted); padding: 0 6px; }

@media (max-width: 760px) {
  .fb-row { grid-template-columns: 1fr; }
  .fb-actions { justify-content: flex-start; }
  .fb-head, .fb-row, .fb-toggle { padding-left: 14px; padding-right: 14px; }
}
@media (prefers-reduced-motion: reduce) {
  .fire-banner-live { animation: none; box-shadow: 0 3px 14px color-mix(in srgb, var(--fire-alarm) 45%, transparent); }
}
</style>
