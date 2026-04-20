<template>
  <div class="page">
    <div class="page-header">
      <h2>{{ t('nav.about') }}</h2>
    </div>

    <div class="card about-card">
      <div class="about-logo">
        <img src="../assets/asp-logo-1.png" class="about-logo-img" alt="ASP logo" />
        <h1 class="app-name">Bee With Me</h1>
        <span class="version">v1.0.0</span>
      </div>

      <div class="about-section">
        <h3>{{ t('about.description') }}</h3>
        <p>Offline people-tracking application for LoRaWAN-based rescue operations.</p>
      </div>

      <div class="about-section">
        <h3>{{ t('about.contact') }}</h3>
        <p>Konstantin Velev<br>Phone: 0877389417<br>Email: konsvelev@gmail.com</p>
        <p style="margin-top:8px">Kiril Penev</p>
      </div>

      <div class="about-section">
        <h3>{{ t('about.team') }}</h3>
        <p>ASP RESCUER TEAM<br><a href="https://rescuer.team" target="_blank" rel="noopener">https://rescuer.team</a></p>
      </div>

      <div class="about-section">
        <h3>{{ t('about.license') }}</h3>
        <p class="placeholder-text">—</p>
      </div>

      <div class="about-section" v-if="authStore.user?.role === 'admin'">
        <h3>{{ t('about.offlineMaps') }}</h3>
        <p style="margin-bottom:12px">{{ t('about.offlineMapsDesc') }}</p>

        <div class="mode-row">
          <span class="mode-label">{{ t('about.offlineMapsMode') }}</span>
          <div class="mode-pills">
            <button
              type="button"
              :class="['mode-pill', !bgMountainsOffline && 'mode-pill-active']"
              @click="bgMountainsOffline = false"
            >{{ t('about.modeOnline') }}</button>
            <button
              type="button"
              :class="['mode-pill', bgMountainsOffline && 'mode-pill-active']"
              @click="bgMountainsOffline = true"
            >{{ t('about.modeOffline') }}</button>
          </div>
        </div>

        <div v-if="tileStatus" class="tile-status">
          <div class="tile-progress-bar">
            <div class="tile-progress-fill" :style="{ width: progressPct + '%' }"></div>
          </div>
          <div class="tile-progress-label">
            <span v-if="tileStatus.running">
              {{ tileStatus.done.toLocaleString() }} / {{ tileStatus.total.toLocaleString() }} &nbsp;·&nbsp; {{ progressPct }}%
            </span>
            <span v-else-if="tileStatus.total > 0" class="tile-done">
              ✓ {{ t('about.offlineMapsComplete') }} &nbsp;·&nbsp; {{ tileStatus.skipped.toLocaleString() }} {{ t('about.offlineMapsSkipped') }}
              <span v-if="tileStatus.errors > 0" class="tile-errors">&nbsp;·&nbsp; {{ tileStatus.errors }} {{ t('about.offlineMapsErrors') }}</span>
            </span>
          </div>
        </div>

        <button :disabled="tileStatus?.running" @click="startDownload" style="margin-top:12px">
          {{ tileStatus?.running ? t('about.offlineMapsDownloading') : t('about.offlineMapsDownload') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'
import { useSettings } from '../composables/useSettings'
import { startTileDownload, getTileStatus } from '../api'

const { t } = useI18n()
const authStore = useAuthStore()
const { bgMountainsOffline } = useSettings()

onMounted(async () => {
  if (!authStore.user) await authStore.fetchMe()
})

const tileStatus = ref(null)
let pollTimer = null

const progressPct = computed(() => {
  if (!tileStatus.value?.total) return 0
  return Math.round(tileStatus.value.done / tileStatus.value.total * 100)
})

async function startDownload() {
  await startTileDownload()
  pollStatus()
}

async function pollStatus() {
  tileStatus.value = await getTileStatus()
  if (tileStatus.value.running) {
    pollTimer = setTimeout(pollStatus, 1500)
  }
}

onUnmounted(() => clearTimeout(pollTimer))
</script>

<style scoped>
.page { padding: 24px; flex: 1; }

.about-card {
  max-width: 640px;
  padding: 36px;
}

.about-logo {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 32px;
  padding-bottom: 24px;
  border-bottom: 1px solid var(--border);
}
.about-logo-img { width: 52px; height: 52px; object-fit: contain; }
.app-name   { font-size: 22px; font-weight: 700; margin: 0; }
.version    { font-size: 12px; color: var(--text-muted); margin-left: auto; }

.about-section {
  margin-bottom: 24px;
}
.about-section h3 {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: .05em;
  margin-bottom: 6px;
}
.about-section p {
  font-size: 14px;
  color: var(--text);
  line-height: 1.6;
  white-space: pre-line;
}
.placeholder-text { color: var(--text-muted); }

.tile-status { margin-top: 8px; }
.tile-progress-bar { height: 6px; background: var(--border); border-radius: 3px; overflow: hidden; }
.tile-progress-fill { height: 100%; background: #3b82f6; border-radius: 3px; transition: width .4s; }
.tile-progress-label { font-size: 13px; color: var(--text-muted); margin-top: 6px; }
.tile-done  { color: var(--success); }
.tile-errors { color: var(--danger); }

.mode-row   { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.mode-label { font-size: 14px; color: var(--text); white-space: nowrap; }
.mode-pills { display: flex; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; flex-shrink: 0; }
.mode-pill  { padding: 5px 16px; font-size: 13px; background: transparent; border: none; color: var(--text-muted); cursor: pointer; }
.mode-pill-active { background: var(--primary, #3b82f6); color: #fff; font-weight: 600; }
</style>
