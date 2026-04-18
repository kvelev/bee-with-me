<template>
  <Teleport to="body">
    <TransitionGroup name="sos-toast" tag="div" class="sos-toast-stack">
      <div
        v-for="n in store.sosNotifications"
        :key="n.id"
        class="sos-toast"
      >
        <div class="sos-toast-icon">🚨</div>
        <div class="sos-toast-body">
          <div class="sos-toast-title">{{ t('sos.alertTitle') }}</div>
          <div class="sos-toast-name">{{ n.name }}</div>
          <div class="sos-toast-time">{{ formatTime(n.timestamp) }}</div>
        </div>
        <button class="sos-toast-close" @click="dismiss(n.id)">✕</button>
      </div>
    </TransitionGroup>
  </Teleport>
</template>

<script setup>
import { watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useLocationsStore } from '../stores/locations'

const { t } = useI18n()
const store = useLocationsStore()

function dismiss(id) {
  store.dismissSOSNotification(id)
}

function formatTime(ts) {
  return new Date(ts).toLocaleTimeString()
}

function playAlarm() {
  try {
    const ctx = new AudioContext()
    const gain = ctx.createGain()
    gain.connect(ctx.destination)
    gain.gain.setValueAtTime(0.25, ctx.currentTime)

    ;[0, 0.18, 0.36].forEach((offset) => {
      const osc = ctx.createOscillator()
      osc.connect(gain)
      osc.frequency.setValueAtTime(880, ctx.currentTime + offset)
      osc.frequency.setValueAtTime(1320, ctx.currentTime + offset + 0.09)
      osc.start(ctx.currentTime + offset)
      osc.stop(ctx.currentTime + offset + 0.16)
    })

    gain.gain.setValueAtTime(0.25, ctx.currentTime + 0.54)
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.7)
  } catch { /* audio not available */ }
}

// Auto-dismiss after 10 s and play alarm on each new notification
watch(
  () => store.sosNotifications.length,
  (newLen, oldLen) => {
    if (newLen <= oldLen) return
    const newest = store.sosNotifications[store.sosNotifications.length - 1]
    playAlarm()
    setTimeout(() => store.dismissSOSNotification(newest.id), 10000)
  },
)
</script>

<style scoped>
.sos-toast-stack {
  position: fixed;
  top: 20px;
  right: 20px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 10px;
  pointer-events: none;
}

.sos-toast {
  pointer-events: all;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  background: #1a0505;
  border: 2px solid #ef4444;
  border-radius: 10px;
  padding: 14px 16px;
  min-width: 280px;
  max-width: 340px;
  box-shadow: 0 0 24px rgba(239, 68, 68, 0.5), 0 4px 16px rgba(0,0,0,0.6);
  animation: sos-pulse-border 1s ease-in-out infinite alternate;
}

@keyframes sos-pulse-border {
  from { box-shadow: 0 0 12px rgba(239,68,68,0.4), 0 4px 16px rgba(0,0,0,0.6); }
  to   { box-shadow: 0 0 32px rgba(239,68,68,0.9), 0 4px 16px rgba(0,0,0,0.6); }
}

.sos-toast-icon { font-size: 22px; flex-shrink: 0; margin-top: 1px; }

.sos-toast-body { flex: 1; min-width: 0; }

.sos-toast-title {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .08em;
  color: #ef4444;
  margin-bottom: 3px;
}

.sos-toast-name {
  font-size: 15px;
  font-weight: 700;
  color: #fff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sos-toast-time {
  font-size: 11px;
  color: rgba(255,255,255,0.5);
  margin-top: 2px;
}

.sos-toast-close {
  background: none;
  border: none;
  color: rgba(255,255,255,0.4);
  font-size: 13px;
  padding: 0;
  cursor: pointer;
  flex-shrink: 0;
  line-height: 1;
  margin-top: 2px;
}
.sos-toast-close:hover { color: #fff; }

.sos-toast-enter-active { transition: all .25s ease; }
.sos-toast-leave-active { transition: all .3s ease; }
.sos-toast-enter-from   { opacity: 0; transform: translateX(40px); }
.sos-toast-leave-to     { opacity: 0; transform: translateX(40px); }
</style>
