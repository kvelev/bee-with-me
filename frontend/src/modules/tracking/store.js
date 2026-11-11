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

// The position/status fields of a thin location_update (plan section 1.4). A live-newer row wins these over an
// older /live answer; everything else (name, rank, photo, phone, groups) is identity and comes from the answer.
const THIN_KEYS = [
  'device_id', 'user_id', 'mgrs', 'latitude', 'longitude', 'altitude_m', 'speed_knots', 'course_deg',
  'battery_voltage', 'gnss_satellites', 'gnss_valid', 'sos_active', 'repeater_mode', 'recorded_at', 'received_at',
]

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

  // Ordering of live messages against requests. A counter, not the clock: two events in the same
  // millisecond still have an order. `liveSeq[deviceId]` = the tick of the last applied live message.
  let seq = 0
  const liveSeq = {}
  // identity fields a full message carried (beyond the thin keys), per device, with the tick it arrived
  const carried = {}

  /** Replace the picture with the /live answer, except that a device whose live message arrived
   *  after this request started keeps its row: the answer is older than that message. The answer's
   *  fields are merged under the row, so a name the message lacks still arrives. */
  async function fetchLive() {
    const startedAt = ++seq
    const rows = await getLivePositions()
    const isNewer = id => (liveSeq[id] ?? 0) > startedAt
    const next = {}
    for (const r of rows) {
      const row = isNewer(r.device_id) ? positions.value[r.device_id] : null
      let merged = r
      if (row) {
        merged = { ...r }
        const own = carried[r.device_id]
        for (const key of Object.keys(row)) {
          if (THIN_KEYS.includes(key) || (own && own.seq > startedAt && own.keys.has(key))) merged[key] = row[key]
        }
      }
      next[r.device_id] = normaliseGroups(merged)
    }
    for (const [id, row] of Object.entries(positions.value)) {
      if (!(id in next) && isNewer(id)) next[id] = row
    }
    positions.value = next
    markSynced()
    saveSnapshot(positions.value)
  }

  // Single-flight roster refresh: one /live request at a time, at most one queued behind it.
  let rosterRunning = false
  let rosterQueued  = false
  async function requestRoster() {
    if (rosterRunning) { rosterQueued = true; return }
    rosterRunning = true
    try {
      do {
        rosterQueued = false
        try { await fetchLive() } catch { /* the resync tick repeats it */ }
      } while (rosterQueued)
    } finally {
      rosterRunning = false
    }
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
    delete liveSeq[deviceId]
    delete carried[deviceId]
    const { [deviceId]: _removedTrail, ...restTrails } = trails.value
    trails.value = restTrails
  }

  function applyLocationUpdate(message) {
    const known = positions.value[message.device_id]
    const existing = known ?? {}
    // A hook that throws is logged and skipped: it must not drop the whole frame.
    const data = updateHooks.reduce((d, fn) => {
      try { return fn(d, existing) ?? d } catch (e) {
        console.error('tracking update hook failed: %s', e?.message ?? String(e))
        return d
      }
    }, message)

    positions.value[data.device_id] = normaliseGroups({ ...existing, ...data })
    liveSeq[data.device_id] = ++seq
    const extra = Object.keys(data).filter(k => k !== 'type' && !THIN_KEYS.includes(k))
    if (extra.length) {
      const prev = carried[data.device_id]
      carried[data.device_id] = { seq, keys: new Set([...(prev?.keys ?? []), ...extra]) }
    }
    markSynced()
    saveSnapshot(positions.value)

    // A thin message has no name: a device we do not hold, or one handed to another person, needs /live.
    if (!known || (data.user_id !== undefined && known.user_id !== data.user_id)) requestRoster()

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
