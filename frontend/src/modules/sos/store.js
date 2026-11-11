import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getOpenSOS, resolveSOS as apiResolve } from '../../api'
import { useTrackingStore } from '../tracking/index.js'

const NAME_KEYS = ['full_name', 'rank', 'device_name', 'dev_sn']

export const useSosStore = defineStore('sos', () => {
  const sosAlerts        = ref([])
  const sosNotifications = ref([])   // [{id, device_id, name, timestamp}]
  // devices whose SOS was manually resolved — suppress re-trigger until device clears SOS itself
  const resolvedSOS      = new Set()

  const hasSOS = computed(() => sosAlerts.value.length > 0)

  const tracking = useTrackingStore()
  // Runs on every location message before the tracking store merges it: decides the effective SOS flag
  // and raises the toast on a rising edge.
  tracking.addUpdateHook((data, existing) => {
    // If the device cleared its SOS on the hardware side, lift the suppression
    if (!data.sos_active) resolvedSOS.delete(data.device_id)

    // Effective SOS: raw flag AND not manually resolved by operator
    const effectiveSOS = data.sos_active && !resolvedSOS.has(data.device_id)

    if (effectiveSOS && !existing.sos_active) {
      // a thin message has no name, and an explicit null is no name either: take it from the row we hold
      const row = { ...existing, ...data }
      for (const key of NAME_KEYS) if (data[key] == null && existing[key] != null) row[key] = existing[key]
      sosNotifications.value.push({
        id:        Date.now() + Math.random(),
        device_id: data.device_id,
        name:      row.full_name || row.device_name || `SN:${row.dev_sn ?? ''}`,
        timestamp: new Date().toISOString(),
      })
    }
    return { ...data, sos_active: effectiveSOS }
  })

  // Ordering of pushed alerts against reads. A counter, not a shared set that reads clear: every read keeps
  // an alert pushed after that read started, however many reads overlap. `pushSeq[deviceId]` = tick of the last push.
  let seq = 0
  const pushSeq = {}

  async function fetchSOS() {
    const startedAt = ++seq
    const rows = await getOpenSOS()
    if (!Array.isArray(rows)) return
    const kept = sosAlerts.value.filter(a => (pushSeq[a.device_id] ?? 0) > startedAt && !rows.some(r => r.device_id === a.device_id))
    sosAlerts.value = [...rows, ...kept]
  }

  function dismissSOSNotification(id) {
    sosNotifications.value = sosNotifications.value.filter(n => n.id !== id)
  }

  function forgetDevice(deviceId) {
    sosAlerts.value = sosAlerts.value.filter(a => a.device_id !== deviceId)
    resolvedSOS.delete(deviceId)
    delete pushSeq[deviceId]
  }

  // Single-flight completion read: one /sos request at a time, at most one queued behind it. A failure is
  // swallowed and never touches the alerts that are already shown.
  let sosRunning = false
  let sosQueued  = false
  async function requestSOS() {
    if (sosRunning) { sosQueued = true; return }
    sosRunning = true
    try {
      do {
        sosQueued = false
        try { await fetchSOS() } catch { /* keep what is shown */ }
      } while (sosQueued)
    } finally {
      sosRunning = false
    }
  }

  function applySOSAlert(data) {
    const { type, ...pushed } = data
    // A thin alert has no name: fill what is missing from the tracking position of that device.
    // A field that is present wins.
    const pos = tracking.positions[pushed.device_id] ?? {}
    const alert = { ...pushed }
    for (const key of NAME_KEYS) {
      if (alert[key] == null && pos[key] != null) alert[key] = pos[key]
    }
    pushSeq[alert.device_id] = ++seq
    showAlert(alert)
    requestSOS()
  }

  function showAlert(alert) {
    const idx = sosAlerts.value.findIndex(a => a.device_id === alert.device_id)
    if (idx === -1) {
      sosAlerts.value.push(alert)
      return
    }
    // Merge rather than skip: an entry seeded from an earlier push may be missing the
    // fields the banner's Resolve button needs. Losing the alert id here is what left an
    // SOS with no way to clear it from the UI.
    // A null name field does not blank a name we already hold.
    const incoming = { ...alert }
    for (const key of NAME_KEYS) if (incoming[key] == null) delete incoming[key]
    sosAlerts.value[idx] = { ...sosAlerts.value[idx], ...incoming }
  }

  async function resolveSOS(alertId, notes) {
    if (!alertId) throw new Error('Cannot resolve: this alert has no id')
    const alert = sosAlerts.value.find(a => a.id === alertId)
    await apiResolve(alertId, notes)
    sosAlerts.value = sosAlerts.value.filter(a => a.id !== alertId)
    if (alert?.device_id) {
      resolvedSOS.add(alert.device_id)
      tracking.patchPosition(alert.device_id, { sos_active: false })
    }
  }

  return {
    sosAlerts, sosNotifications, hasSOS,
    fetchSOS, applySOSAlert, resolveSOS, dismissSOSNotification, forgetDevice,
  }
})
