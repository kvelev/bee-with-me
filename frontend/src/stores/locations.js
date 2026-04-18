import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getLivePositions, getOpenSOS, resolveSOS as apiResolve, getTrail } from '../api'

const TRAIL_MINUTES = 30
const TRAIL_MS = TRAIL_MINUTES * 60 * 1000

export const useLocationsStore = defineStore('locations', () => {
  // Keyed by device_id for O(1) updates from WebSocket
  const positions        = ref({})
  const sosAlerts        = ref([])
  const sosNotifications = ref([])   // [{id, device_id, name, timestamp}]
  const trails           = ref({})
  const serialStatus     = ref(null)
  // devices whose SOS was manually resolved — suppress re-trigger until device clears SOS itself
  const resolvedSOS      = new Set()

  const positionList = computed(() => Object.values(positions.value))
  const hasSOS       = computed(() => sosAlerts.value.length > 0)

  async function fetchLive() {
    const rows = await getLivePositions()
    positions.value = Object.fromEntries(rows.map(r => [r.device_id, r]))
  }

  async function fetchSOS() {
    sosAlerts.value = await getOpenSOS()
  }

  async function fetchTrail() {
    trails.value = await getTrail(TRAIL_MINUTES)
  }

  function dismissSOSNotification(id) {
    sosNotifications.value = sosNotifications.value.filter(n => n.id !== id)
  }

  function applyLocationUpdate(data) {
    const existing = positions.value[data.device_id] ?? {}

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

    positions.value[data.device_id] = { ...existing, ...data, sos_active: effectiveSOS }

    // Append to trail and prune points older than 30 min
    if (data.latitude == null || data.longitude == null) return
    const point = { lat: data.latitude, lon: data.longitude, recorded_at: data.recorded_at ?? new Date().toISOString() }
    const prev  = trails.value[data.device_id] ?? []
    const cutoff = Date.now() - TRAIL_MS
    trails.value[data.device_id] = [
      ...prev.filter(p => new Date(p.recorded_at).getTime() > cutoff),
      point,
    ]
  }

  function applySerialStatus(data) {
    const { type, ...s } = data
    serialStatus.value = s
  }

  function applySOSAlert(data) {
    const already = sosAlerts.value.some(a => a.device_id === data.device_id)
    if (!already) sosAlerts.value.push(data)
  }

  async function resolveSOS(alertId, notes) {
    const alert = sosAlerts.value.find(a => a.id === alertId)
    await apiResolve(alertId, notes)
    sosAlerts.value = sosAlerts.value.filter(a => a.id !== alertId)
    if (alert?.device_id) {
      resolvedSOS.add(alert.device_id)
      if (positions.value[alert.device_id]) {
        positions.value[alert.device_id] = { ...positions.value[alert.device_id], sos_active: false }
      }
    }
  }

  return {
    positions, sosAlerts, sosNotifications, trails, serialStatus, positionList, hasSOS,
    fetchLive, fetchSOS, fetchTrail,
    applyLocationUpdate, applySOSAlert, applySerialStatus, resolveSOS, dismissSOSNotification,
  }
})
