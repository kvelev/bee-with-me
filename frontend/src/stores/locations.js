import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getLivePositions, getOpenSOS, resolveSOS as apiResolve, getTrail } from '../api'
import { contactAt, freshnessOf, LOST, STALE } from '../lib/freshness'

const TRAIL_MINUTES = 30
const TRAIL_MS = TRAIL_MINUTES * 60 * 1000

const SNAPSHOT_KEY = 'bwm.positions.snapshot'

/** Last known picture, kept so a reload paints immediately instead of showing an empty
 *  map while the first request is in flight. Restored positions keep their original
 *  received_at, so they render with their true age — cached, never passed off as live. */
function loadSnapshot() {
  try {
    const raw = localStorage.getItem(SNAPSHOT_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed?.positions || typeof parsed.positions !== 'object') return null
    return parsed
  } catch { return null }
}

function saveSnapshot(positions) {
  try {
    localStorage.setItem(SNAPSHOT_KEY, JSON.stringify({
      savedAt: new Date().toISOString(),
      positions,
    }))
  } catch { /* private window, quota, or storage disabled — the map still works */ }
}

export const useLocationsStore = defineStore('locations', () => {
  const snapshot = loadSnapshot()

  // Keyed by device_id for O(1) updates from WebSocket
  const positions        = ref(snapshot?.positions ?? {})
  const sosAlerts        = ref([])
  const sosNotifications = ref([])   // [{id, device_id, name, timestamp}]
  const trails           = ref({})
  const serialStatus     = ref(null)
  // devices whose SOS was manually resolved — suppress re-trigger until device clears SOS itself
  const resolvedSOS      = new Set()

  // Connection/freshness bookkeeping for the "showing cached data" banner
  const wsConnected  = ref(false)
  const lastSyncAt   = ref(snapshot?.savedAt ?? null)
  const fromSnapshot = ref(!!snapshot)

  const positionList = computed(() => Object.values(positions.value))
  const hasSOS       = computed(() => sosAlerts.value.length > 0)

  /** Devices we've stopped hearing from. Not an emergency on its own — a rescuer can walk
   *  behind a ridge — but the operator has to be able to see it without hunting. */
  const silentList = computed(() => {
    const now = Date.now()
    return positionList.value
      .filter(p => !p.sos_active)
      .filter(p => [STALE, LOST].includes(freshnessOf(p, now)))
  })
  const lostList = computed(() => {
    const now = Date.now()
    return positionList.value.filter(p => freshnessOf(p, now) === LOST)
  })

  function markSynced() {
    lastSyncAt.value   = new Date().toISOString()
    fromSnapshot.value = false
  }

  function setConnected(connected) {
    wsConnected.value = connected
  }

  async function fetchLive() {
    const rows = await getLivePositions()
    positions.value = Object.fromEntries(rows.map(r => [r.device_id, r]))
    markSynced()
    saveSnapshot(positions.value)
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

  function resetTrail(deviceId) {
    // Call when a device's volunteer assignment changes — the marker/live position stays,
    // but the accumulated trail line must not splice the previous holder's path into the
    // new one's.
    const { [deviceId]: _removedTrail, ...rest } = trails.value
    trails.value = rest
  }

  function removePosition(deviceId) {
    const { [deviceId]: _removed, ...rest } = positions.value
    positions.value = rest
    const { [deviceId]: _removedTrail, ...restTrails } = trails.value
    trails.value = restTrails
    sosAlerts.value = sosAlerts.value.filter(a => a.device_id !== deviceId)
    resolvedSOS.delete(deviceId)
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
    markSynced()
    saveSnapshot(positions.value)

    // A frame with no GNSS fix carries the last known position forward — it proves contact,
    // not movement. Recording it as a new trail point would draw a line the rescuer never
    // walked, so update the marker and stop here.
    if (data.gnss_valid === false) return

    // Append to trail and prune points older than 30 min. Both the timestamp we prune on and
    // the one we label checkpoints with are the server's, so a device with a bad clock can't
    // erase its own trail or stamp it with times that never happened.
    if (data.latitude == null || data.longitude == null) return
    const stamp = data.received_at ?? data.recorded_at ?? new Date().toISOString()
    const point = {
      lat: data.latitude,
      lon: data.longitude,
      recorded_at: data.recorded_at ?? stamp,
      received_at: stamp,
    }
    const prev  = trails.value[data.device_id] ?? []
    const cutoff = Date.now() - TRAIL_MS
    trails.value[data.device_id] = [
      ...prev.filter(p => contactAt(p) > cutoff),
      point,
    ]
  }

  function applySerialStatus(data) {
    const { type, ...s } = data
    serialStatus.value = s
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
      if (positions.value[alert.device_id]) {
        positions.value[alert.device_id] = { ...positions.value[alert.device_id], sos_active: false }
      }
    }
  }

  return {
    positions, sosAlerts, sosNotifications, trails, serialStatus, positionList, hasSOS,
    wsConnected, lastSyncAt, fromSnapshot, silentList, lostList,
    fetchLive, fetchSOS, fetchTrail, setConnected,
    applyLocationUpdate, applySOSAlert, applySerialStatus, resolveSOS, dismissSOSNotification,
    removePosition, resetTrail,
  }
})
