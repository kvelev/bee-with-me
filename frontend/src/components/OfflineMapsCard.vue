<template>
  <section class="card offline-maps" aria-labelledby="offline-maps-title" data-testid="offline-maps">
    <h3 id="offline-maps-title" class="section-title">{{ t('settings.offlineMaps.title') }}</h3>

    <!-- Not a server setting: applies to this browser at once, no Save needed (composables/useSettings.js) -->
    <fieldset class="mode" data-testid="bgm-mode" aria-describedby="bgm-hint">
      <legend>{{ t('settings.offlineMaps.mode') }}</legend>
      <label><input type="radio" name="bgm-mode" value="online" :checked="!bgMountainsOffline"
                    @change="setBgMountainsOffline(false)" /> {{ t('settings.offlineMaps.online') }}</label>
      <label><input type="radio" name="bgm-mode" value="offline" :checked="bgMountainsOffline"
                    @change="setBgMountainsOffline(true)" /> {{ t('settings.offlineMaps.offline') }}</label>
    </fieldset>
    <p id="bgm-hint" class="hint">{{ t('settings.offlineMaps.modeHint') }}</p>

    <p class="desc">{{ t('settings.offlineMaps.desc') }}</p>
    <p v-if="tileStatus && !tileStatus.running && !tileStatus.total" class="hint" data-testid="tiles-available">
      {{ tileStatus.available ? t('settings.offlineMaps.available') : t('settings.offlineMaps.notAvailable') }}
    </p>

    <div v-if="tileStatus?.running || tileStatus?.total" class="tile-status">
      <div class="tile-progress-bar">
        <div class="tile-progress-fill" :style="{ transform: 'scaleX(' + progressPct / 100 + ')' }"></div>
      </div>
      <div class="tile-progress-label">
        <span v-if="tileStatus.running">
          {{ tileStatus.done.toLocaleString() }} / {{ tileStatus.total.toLocaleString() }} &nbsp;·&nbsp; {{ progressPct }}%
        </span>
        <span v-else class="tile-done">
          ✓ {{ t('settings.offlineMaps.complete') }} &nbsp;·&nbsp; {{ tileStatus.skipped.toLocaleString() }} {{ t('settings.offlineMaps.skipped') }}
          <span v-if="tileStatus.errors > 0" class="tile-errors">&nbsp;·&nbsp; {{ tileStatus.errors }} {{ t('settings.offlineMaps.errors') }}</span>
        </span>
      </div>
    </div>

    <button type="button" class="download-btn" data-testid="tiles-download" :disabled="tileStatus?.running" @click="openPasswordPrompt">
      {{ tileStatus?.running ? t('settings.offlineMaps.downloading') : t('settings.offlineMaps.download') }}
    </button>

    <div v-if="passwordPromptOpen" class="modal-backdrop" @click.self="closePasswordPrompt">
      <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="tiles-pw-title">
        <h3 id="tiles-pw-title" class="modal-title">{{ t('settings.offlineMaps.passwordTitle') }}</h3>
        <p class="modal-desc">{{ t('settings.offlineMaps.passwordDesc') }}</p>
        <input
          ref="passwordInputEl"
          v-model="passwordInput"
          type="password"
          class="modal-input"
          :placeholder="t('settings.offlineMaps.passwordPlaceholder')"
          @keyup.enter="submitPassword"
        />
        <div v-if="passwordError" class="modal-error" role="alert">{{ passwordError }}</div>
        <div class="modal-actions">
          <button type="button" class="secondary" @click="closePasswordPrompt">{{ t('common.cancel') }}</button>
          <button type="button" :disabled="!passwordInput" @click="submitPassword">{{ t('settings.offlineMaps.download') }}</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { getTileStatus, startTileDownload } from '../api'
import { errorText } from '../api/client'
import { useSettings } from '../composables/useSettings'

const { t } = useI18n()
const { bgMountainsOffline, setBgMountainsOffline, resolveBgMountainsDefault } = useSettings()

const tileStatus = ref(null)
let pollTimer = null

const passwordPromptOpen = ref(false)
const passwordInput      = ref('')
const passwordError      = ref('')
const passwordInputEl    = ref(null)

const progressPct = computed(() => {
  if (!tileStatus.value?.total) return 0
  return Math.round(tileStatus.value.done / tileStatus.value.total * 100)
})

function openPasswordPrompt() {
  passwordInput.value = ''
  passwordError.value = ''
  passwordPromptOpen.value = true
  nextTick(() => passwordInputEl.value?.focus())
}

function closePasswordPrompt() {
  passwordPromptOpen.value = false
}

async function submitPassword() {
  if (!passwordInput.value) return
  passwordError.value = ''
  try {
    await startTileDownload(passwordInput.value)
    passwordPromptOpen.value = false
    pollStatus()
  } catch (e) {
    passwordError.value = e?.status === 403 ? t('settings.offlineMaps.passwordWrong') : errorText(e)
  }
}

async function pollStatus() {
  try {
    tileStatus.value = await getTileStatus()
  } catch {
    return   // status is informational; the download itself runs on the server
  }
  if (tileStatus.value?.running) pollTimer = setTimeout(pollStatus, 1500)
}

onMounted(() => {
  resolveBgMountainsDefault()
  pollStatus()   // shows whether tiles exist, and picks up a download already running
})
onUnmounted(() => clearTimeout(pollTimer))
</script>

<style scoped>
.offline-maps { margin-top: 16px; }
.section-title { font-size: 14px; font-weight: 600; margin-bottom: 12px; color: var(--text-muted); }
.mode { border: 0; padding: 0; margin: 0; display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.mode legend { float: left; margin-right: 8px; font-size: 14px; color: var(--text); }
.mode label { display: inline-flex; align-items: center; gap: 6px; margin: 0; font-size: 14px; color: var(--text); cursor: pointer; }
.hint { font-size: 13px; color: var(--text-muted); margin: 6px 0 12px; }
.desc { font-size: 14px; color: var(--text); line-height: 1.5; margin-bottom: 8px; }
.download-btn { margin-top: 12px; }
.download-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

.tile-status { margin-top: 8px; }
.tile-progress-bar { height: 6px; background: var(--border); border-radius: 3px; overflow: hidden; }
.tile-progress-fill { height: 100%; width: 100%; background: var(--accent); border-radius: 3px; transform-origin: left; transition: transform .4s; }
@media (prefers-reduced-motion: reduce) { .tile-progress-fill { transition: none; } }
.tile-progress-label { font-size: 13px; color: var(--text-muted); margin-top: 6px; }
.tile-done  { color: var(--success); }
.tile-errors { color: var(--danger); }

.modal-backdrop {
  position: fixed; inset: 0; z-index: 100;
  background: rgba(0,0,0,0.55); backdrop-filter: blur(2px);
  display: flex; align-items: center; justify-content: center;
}
.modal-card {
  background: var(--bg-panel); border: 1px solid var(--border); border-radius: 8px;
  padding: 24px; width: min(420px, 90vw);
  box-shadow: 0 12px 40px rgba(0,0,0,0.5);
}
.modal-title { margin: 0 0 8px; font-size: 16px; font-weight: 600; }
.modal-desc  { margin: 0 0 14px; font-size: 13px; color: var(--text-muted); }
.modal-input {
  width: 100%; padding: 8px 10px; font-size: 14px;
  background: var(--bg-card); color: var(--text);
  border: 1px solid var(--border); border-radius: 4px;
  box-sizing: border-box;
}
.modal-input:focus { outline: none; border-color: var(--accent); }
.modal-error { margin-top: 8px; font-size: 12px; color: var(--danger); }
.modal-actions { margin-top: 16px; display: flex; justify-content: flex-end; gap: 8px; }
</style>
