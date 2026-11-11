import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getOpenSOS, resolveSOS as apiResolve } from '../../api'
import { useTrackingStore } from '../tracking/index.js'

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
      sosNotifications.value.push({
        id:        Date.now() + Math.random(),
        device_id: data.device_id,
        name:      data.full_name || data.device_name || `SN:${data.dev_sn ?? ''}`,
        timestamp: new Date().toISOString(),
      })
    }
    return { ...data, sos_active: effectiveSOS }
  })

  async function fetchSOS() {
    sosAlerts.value = await getOpenSOS()
  }

  function dismissSOSNotification(id) {
    sosNotifications.value = sosNotifications.value.filter(n => n.id !== id)
  }

  function forgetDevice(deviceId) {
    sosAlerts.value = sosAlerts.value.filter(a => a.device_id !== deviceId)
    resolvedSOS.delete(deviceId)
  }

  function applySOSAlert(data) {
    const { type, ...alert } = data
    const idx = sosAlerts.value.findIndex(a => a.device_id === alert.device_id)
    if (idx === -1) {
      sosAlerts.value.push(alert)
      return
    }
    // Merge rather than skip: an entry seeded from an earlier push may be missing the
    // fields the banner's Resolve button needs. Losing the alert id here is what left an
    // SOS with no way to clear it from the UI.
    sosAlerts.value[idx] = { ...sosAlerts.value[idx], ...alert }
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
