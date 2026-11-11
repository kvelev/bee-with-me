import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getLivePositions, getTrail } from '../../api'
import { normaliseGroups } from '../../lib/groups'
import { contactAt, freshnessOf, LOST, STALE } from './lib/freshness'

const TRAIL_MINUTES = 30
const TRAIL_MS = TRAIL_MINUTES * 60 * 1000

const SNAPSHOT_KEY = 'bwm.positions.snapshot'

function normalisePositions(map) {
  return Object.fromEntries(Object.entries(map).map(([id, p]) => [id, normaliseGroups(p)]))
}

/** Last known picture, kept so a reload paints immediately instead of showing an empty
 *  map while the first request is in flight. Restored positions keep their original
 *  received_at, so they render with their true age — cached, never passed off as live. */
function loadSnapshot() {
  try {
    const raw = localStorage.getItem(SNAPSHOT_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed?.positions || typeof parsed.positions !== 'object') return null
    return { ...parsed, positions: normalisePositions(parsed.positions) }
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

/** Positions, trails and the connection/freshness state. It does not know the `sos` module: other modules
 *  reach into a message through `addUpdateHook` and into a marker through `patchPosition`. */
export const useTrackingStore = defineStore('tracking', () => {
  const snapshot = loadSnapshot()

  // Keyed by device_id for O(1) updates from WebSocket
  const positions    = ref(snapshot?.positions ?? {})
  const trails       = ref({})
  const serialStatus = ref(null)

  // Connection/freshness bookkeeping for the "showing cached data" banner
  const wsConnected  = ref(false)
  const lastSyncAt   = ref(snapshot?.savedAt ?? null)
  const fromSnapshot = ref(!!snapshot)

  // fn(data, existing) -> data, run before the merge in registration order
  const updateHooks = []

  const positionList = computed(() => Object.values(positions.value))

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
    positions.value = Object.fromEntries(rows.map(r => [r.device_id, normaliseGroups(r)]))
    markSynced()
    saveSnapshot(positions.value)
  }

  async function fetchTrail() {
    trails.value = await getTrail(TRAIL_MINUTES)
  }

  function addUpdateHook(fn) {
    updateHooks.push(fn)
  }

  /** Change fields of one marker, keeping the rest. Nothing happens for an unknown device. */
  function patchPosition(deviceId, fields) {
    const current = positions.value[deviceId]
    if (!current) return
    positions.value[deviceId] = { ...current, ...fields }
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
  }

  function applyLocationUpdate(message) {
    const existing = positions.value[message.device_id] ?? {}
    const data = updateHooks.reduce((d, fn) => fn(d, existing) ?? d, message)

    positions.value[data.device_id] = normaliseGroups({ ...existing, ...data })
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

  return {
    positions, trails, serialStatus, positionList,
    wsConnected, lastSyncAt, fromSnapshot, silentList, lostList,
    fetchLive, fetchTrail, setConnected,
    applyLocationUpdate, applySerialStatus,
    removePosition, resetTrail, addUpdateHook, patchPosition,
  }
})
