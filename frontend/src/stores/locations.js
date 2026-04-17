import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getLivePositions, getOpenSOS, resolveSOS as apiResolve, getTrail } from '../api'

const TRAIL_MINUTES = 30
const TRAIL_MS = TRAIL_MINUTES * 60 * 1000

export const useLocationsStore = defineStore('locations', () => {
  // Keyed by device_id for O(1) updates from WebSocket
  const positions = ref({})
  const sosAlerts = ref([])
  // device_id -> [{lat, lon, recorded_at (ISO string)}]
  const trails    = ref({})

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

  function applyLocationUpdate(data) {
    const existing = positions.value[data.device_id] ?? {}
    positions.value[data.device_id] = { ...existing, ...data }

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

  function applySOSAlert(data) {
    const already = sosAlerts.value.some(a => a.device_id === data.device_id)
    if (!already) sosAlerts.value.push(data)
  }

  async function resolveSOS(alertId, notes) {
    await apiResolve(alertId, notes)
    sosAlerts.value = sosAlerts.value.filter(a => a.id !== alertId)
  }

  return {
    positions, sosAlerts, trails, positionList, hasSOS,
    fetchLive, fetchSOS, fetchTrail,
    applyLocationUpdate, applySOSAlert, resolveSOS,
  }
})
