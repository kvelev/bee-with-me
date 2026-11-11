import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  acknowledgeAllFireAlerts, acknowledgeFireAlert, createFieldReport, createSuppressionZone, disableSuppressionZone,
  dismissFireHotspot, enableSuppressionZone, extinguishFieldReport, getFireAlerts, getFireBurntAreas, getFireHotspots, getSuppressionZones,
  updateSuppressionZone,
} from '../../api'
import { oldestFetchedAt, worstUpstreamState } from './lib/fireStyle'

const LAYERS_KEY = 'bwm.fireLayers'
const EMPTY = () => ({ type: 'FeatureCollection', features: [] })

function loadLayers() {
  try {
    const saved = JSON.parse(localStorage.getItem(LAYERS_KEY) || '{}')
    return { burnt: !!saved.burnt, hotspots: !!saved.hotspots, zones: !!saved.zones }
  } catch {
    return { burnt: false, hotspots: false, zones: false }
  }
}

function saveLayers(layers) {
  try { localStorage.setItem(LAYERS_KEY, JSON.stringify(layers)) } catch { /* private mode: per-session only */ }
}

export const useFireStore = defineStore('fire', () => {
  const hotspots      = ref(EMPTY())
  const burntAreas    = ref(EMPTY())
  // Hotspot feed: also what the WebSocket `fire_data_updated` message reports.
  const fetchedAt     = ref(null)
  const upstreamState = ref('unknown')
  // Burnt-area feed keeps its own as-of time so the pill never claims more than it knows.
  const burntFetchedAt     = ref(null)
  const burntUpstreamState = ref('unknown')
  const layers        = ref(loadLayers())

  const anyLayerOn = computed(() => layers.value.burnt || layers.value.hotspots || layers.value.zones)

  // What the freshness pill shows: only the feeds the operator is looking at, combined
  // pessimistically (oldest time, worst state).
  const shownFeeds = computed(() => {
    const feeds = []
    if (layers.value.hotspots) feeds.push({ at: fetchedAt.value, state: upstreamState.value })
    if (layers.value.burnt)    feeds.push({ at: burntFetchedAt.value, state: burntUpstreamState.value })
    return feeds
  })
  const shownFetchedAt = computed(() => oldestFetchedAt(shownFeeds.value.map(f => f.at)))
  const shownUpstreamState = computed(() => worstUpstreamState(shownFeeds.value.map(f => f.state)))

  // Each feed numbers its requests. The resync tick, `fire_data_updated` and a layer toggle
  // can overlap, and only the newest request may write data or a failure flag: otherwise
  // 08:30 data can replace 09:00 data, or a late timeout can mark current data as failed.
  const hotspotsFailed = ref(false)
  const burntFailed    = ref(false)
  let hotspotsSeq = 0
  let burntSeq = 0
  // The as-of time of the last payload the MAP accepted, per feed. A fetch sets the time
  // optimistically; if the map then rejects the payload (markFeedFailed) the time goes back
  // here, so the pill never claims an age for data that is not drawn (BP-01).
  const accepted = { hotspots: { at: null, state: 'unknown' }, burnt: { at: null, state: 'unknown' } }

  async function fetchHotspots() {
    const seq = ++hotspotsSeq
    try {
      const fc = await getFireHotspots()
      if (seq !== hotspotsSeq) return
      hotspots.value = fc
      accepted.hotspots = { at: fetchedAt.value, state: upstreamState.value }
      fetchedAt.value = fc.fetched_at ?? null
      upstreamState.value = fc.upstream_state ?? 'unknown'
      hotspotsFailed.value = false
    } catch (err) {
      if (seq === hotspotsSeq) hotspotsFailed.value = true
      throw err
    }
  }

  async function fetchBurntAreas() {
    const seq = ++burntSeq
    try {
      const fc = await getFireBurntAreas()
      if (seq !== burntSeq) return
      burntAreas.value = fc
      accepted.burnt = { at: burntFetchedAt.value, state: burntUpstreamState.value }
      burntFetchedAt.value = fc.fetched_at ?? null
      burntUpstreamState.value = fc.upstream_state ?? 'unknown'
      burntFailed.value = false
    } catch (err) {
      if (seq === burntSeq) burntFailed.value = true
      throw err
    }
  }

  // True while the last attempt to reach OUR backend failed for a feed the operator is
  // looking at (distinct from upstream_state, which is the backend's view of EFFIS). The
  // pill shows both as "unavailable".
  const fetchFailed = computed(() =>
    (layers.value.hotspots && hotspotsFailed.value) || (layers.value.burnt && burntFailed.value))

  // The map could not draw a feed it received (unreadable GeoJSON): show it as failed, the
  // same as a failed fetch. The next successful fetch clears it.
  function markFeedFailed(name) {
    if (name === 'hotspots') {
      hotspotsFailed.value = true
      fetchedAt.value = accepted.hotspots.at
      upstreamState.value = accepted.hotspots.state
    }
    if (name === 'burnt') {
      burntFailed.value = true
      burntFetchedAt.value = accepted.burnt.at
      burntUpstreamState.value = accepted.burnt.state
    }
  }

  // Resync tick: re-pull only the shown feeds that are in the failed state. Healthy feeds
  // are left alone (the backend polls EFFIS every 30 min), failed ones recover on their own.
  function retryFailed() {
    const jobs = []
    if (layers.value.hotspots && hotspotsFailed.value) jobs.push(fetchHotspots())
    if (layers.value.burnt && burntFailed.value)       jobs.push(fetchBurntAreas())
    return Promise.all(jobs).then(() => undefined)
  }

  function refreshVisible() {
    const jobs = []
    if (layers.value.hotspots) jobs.push(fetchHotspots())
    if (layers.value.burnt)    jobs.push(fetchBurntAreas())
    return Promise.all(jobs).then(() => undefined)
  }

  function setLayer(name, on) {
    layers.value = { ...layers.value, [name]: !!on }
    saveLayers(layers.value)
    // Turning a layer off cancels its in-flight request: a response (or failure) that lands
    // after the operator hid the layer must not touch the store.
    if (!on && name === 'hotspots') { hotspotsSeq++; hotspotsFailed.value = false }
    if (!on && name === 'burnt')    { burntSeq++;    burntFailed.value = false }
    if (on && name === 'zones') return Promise.all([refreshVisible(), fetchZones()]).then(() => undefined)
    return on ? refreshVisible() : Promise.resolve()
  }

  function applyFireDataUpdated(msg) {
    // The message only says "new data exists": the pill time comes from a fetch the map
    // accepted, never from this message (a failed refetch would otherwise show the new
    // time over old data, or over an empty map).
    void msg
    return refreshVisible()
  }

  // ---- Operator writes: dismiss, field reports, suppression zones ---------------------------------
  // The server answers every write with the changed row, so the store swaps that one row in; the
  // `fire_data_updated` push that follows refreshes the rest. Errors propagate to the caller
  // (ApiError: `.detail`, `.status`); nothing here logs notes, which are free operator text.
  const zones       = ref([])
  const zonesFailed = ref(false)

  function upsertHotspotFeature(next) {
    const features = hotspots.value.features
    const idx = features.findIndex(f => f.id === next.id)
    hotspots.value = {
      ...hotspots.value,
      features: idx === -1 ? [next, ...features] : features.map(f => (f.id === next.id ? next : f)),
    }
  }

  function upsertZone(next) {
    const idx = zones.value.findIndex(z => z.id === next.id)
    zones.value = idx === -1 ? [...zones.value, next] : zones.value.map(z => (z.id === next.id ? next : z))
  }

  async function dismissHotspot(id, notes) {
    upsertHotspotFeature(await dismissFireHotspot(id, notes))
  }

  // A rescuer's position (deviceId) or a point (latitude, longitude): never both in one request.
  async function reportFire({ deviceId, latitude, longitude, notes } = {}) {
    const body = deviceId
      ? { device_id: deviceId, notes: notes ?? null }
      : { latitude, longitude, notes: notes ?? null }
    upsertHotspotFeature(await createFieldReport(body))
  }

  async function extinguish(id) {
    upsertHotspotFeature(await extinguishFieldReport(id))
  }

  // Only the newest request may write the list or the failure flag (a late answer must not
  // replace a newer one, as with the feeds above).
  let zonesSeq = 0
  // The list the view last asked for (Settings lists disabled zones too): a push refetches that same list.
  let zonesWanted = null
  async function fetchZones(includeDisabled = false) {
    const seq = ++zonesSeq
    zonesWanted = includeDisabled
    try {
      const list = await getSuppressionZones({ include_disabled: includeDisabled })
      if (seq !== zonesSeq) return
      zones.value = list
      zonesFailed.value = false
    } catch (err) {
      if (seq === zonesSeq) zonesFailed.value = true
      throw err
    }
  }

  async function createZone(body)     { upsertZone(await createSuppressionZone(body)) }
  async function updateZone(id, body) { upsertZone(await updateSuppressionZone(id, body)) }
  // Activation sends the version the operator saw (`updated_at`); the server answers 409 zone_stale if it moved on.
  async function disableZone(id, expectedUpdatedAt) { upsertZone(await disableSuppressionZone(id, expectedUpdatedAt)) }
  async function enableZone(id, expectedUpdatedAt)  { upsertZone(await enableSuppressionZone(id, expectedUpdatedAt)) }

  // WebSocket `fire_zones_updated`: a zone was written (here or elsewhere). Refetch the zone list the
  // view holds (only if one was ever loaded) and the shown hotspots, whose suppression state changed (BP-02).
  function applyFireZonesUpdated() {
    const jobs = [refreshVisible()]
    if (zonesWanted !== null) jobs.push(fetchZones(zonesWanted))
    return Promise.allSettled(jobs).then((results) => {
      const failed = results.find(r => r.status === 'rejected')
      if (failed) throw failed.reason
    })
  }

  // ---- Fire alarms (alerts near HQ or a rescuer) --------------------------------------------
  // Open alerts, acknowledged ones included: an acknowledged alert stays listed (quiet) until
  // it is resolved (BP-02). `ringToken` goes up exactly when the tone must play once.
  const alerts       = ref([])
  const ringToken    = ref(0)
  const alertsFailed = ref(false)   // the last load of the open alerts failed: the list may be incomplete (BP-01)
  // Open alerts the server holds beyond what the last load returned (its row limit): the banner
  // says so instead of silently showing a partial list (BP-01, BP-02).
  const alertsHidden = ref(0)
  const unacknowledged = computed(() => alerts.value.filter(a => !a.acknowledged_at))

  // "Show on map": MapView consumes it (centres, then clears it).
  const focusRequest = ref(null)
  let focusSeq = 0
  function requestFocus(latitude, longitude) {
    focusRequest.value = { latitude, longitude, n: ++focusSeq }
  }
  function clearFocusRequest() { focusRequest.value = null }

  // A load that was in flight while a WebSocket message or an acknowledge changed the list must
  // not undo that change when it lands (an older snapshot would drop a new alert or bring an
  // acknowledged one back). Changes made meanwhile are logged and replayed over the snapshot.
  let alertsSeq = 0
  let alertsInflight = 0
  let alertsLog = []

  // The first load (page open, login) restores alarms silently; every later load that brings an
  // unacknowledged alert nobody has been told about rings (a lost push must not mean a silent alarm).
  // `seen` holds every id a load has listed; `rang` every id a tone was played for. A push that
  // follows a fetch (or the other way round) never rings twice and never goes missing: a push
  // for an alert only the silent first load listed still rings, because a reload brings no pushes.
  let alertsLoadedOnce = false
  const seen = new Set()
  const rang = new Set()

  // Several alerts in one tick, or a fetch and a push for the same event, play ONE tone: a ring
  // is dropped when another started less than RING_GAP_MS ago (the tone is about 1.3 s long).
  const RING_GAP_MS = 1500
  let lastRingAt = -Infinity
  const ring = () => {
    // Monotonic clock: a backwards step of the OS clock must never mute the alarm (BP-02).
    const at = performance.now()
    if (at - lastRingAt < RING_GAP_MS) return
    lastRingAt = at
    ringToken.value += 1
  }
  const clean = ({ type, ...rest }) => { void type; return rest }   // drop the WebSocket envelope key

  function upsertAlert(next) {
    next = clean(next)
    // Resolved means gone, whichever way the row reached us (push, acknowledge response).
    if (next.resolved_at) { removeAlert(next.id); return false }
    if (alertsInflight) alertsLog.push({ id: next.id, remove: false })
    const idx = alerts.value.findIndex(a => a.id === next.id)
    if (idx === -1) {
      alerts.value = [...alerts.value, next]
      return true
    }
    // Acknowledged stays acknowledged until resolved: a late or reordered message never re-arms it.
    const keepAck = alerts.value[idx].acknowledged_at && !next.acknowledged_at
    alerts.value = alerts.value.map(a => (a.id === next.id
      ? { ...a, ...next, ...(keepAck ? { acknowledged_at: a.acknowledged_at } : {}) }
      : a))
    return false
  }

  function removeAlert(id) {
    if (alertsInflight) alertsLog.push({ id, remove: true })
    alerts.value = alerts.value.filter(a => a.id !== id)
  }

  async function fetchOpenAlerts() {
    const seq = ++alertsSeq
    const from = alertsLog.length
    alertsInflight += 1
    try {
      const fetched = await getFireAlerts({ state: 'open' })
      if (seq !== alertsSeq) return
      const total = Number.isFinite(fetched.total) ? fetched.total : fetched.length
      const local = new Map(alerts.value.map(a => [a.id, a]))
      let next = fetched.map(a => {
        const mine = local.get(a.id)
        return mine?.acknowledged_at && !a.acknowledged_at ? { ...a, acknowledged_at: mine.acknowledged_at } : a
      })
      for (const change of alertsLog.slice(from)) {
        next = next.filter(a => a.id !== change.id)
        const mine = alerts.value.find(a => a.id === change.id)
        if (!change.remove && mine) next.push(mine)
      }
      alerts.value = next
      alertsFailed.value = false
      alertsHidden.value = Math.max(0, total - fetched.length)
      const fresh = next.filter(a => !a.acknowledged_at && !seen.has(a.id) && !rang.has(a.id))
      for (const a of next) seen.add(a.id)
      if (alertsLoadedOnce && fresh.length) {
        for (const a of fresh) rang.add(a.id)
        ring()
      }
      alertsLoadedOnce = true
    } catch (err) {
      if (seq === alertsSeq) {
        alertsFailed.value = true
        // A failed first load told the operator nothing: the next success compares against the
        // empty baseline and rings for what is unacknowledged (BP-01, BP-02).
        alertsLoadedOnce = true
      }
      throw err
    } finally {
      alertsInflight -= 1
      if (!alertsInflight) alertsLog = []
    }
  }

  function applyFireAlert(msg) {
    if (msg.resolved_at) return
    upsertAlert(msg)
    const told = msg.acknowledged_at || rang.has(msg.id)
    rang.add(msg.id)
    if (!told) ring()
  }

  // One repeat message lists every alert that is due: one tone, however many ids it holds.
  async function applyFireAlertRepeat({ alert_ids: ids = [] }) {
    const known = new Map(alerts.value.map(a => [a.id, a]))
    if (ids.some(id => !known.has(id))) {
      // The server repeats only open, unacknowledged alerts. An id we do not list is either hidden
      // beyond the row limit or lost to a failed load: it rings. Only a successful full reload that
      // no longer lists it (resolved meanwhile) keeps quiet.
      let reloaded = false
      try { await fetchOpenAlerts(); reloaded = true } catch { /* alertsFailed is set; ring anyway */ }
      const unlisted = ids.some(id => !alerts.value.some(a => a.id === id))
      const open = ids.some(id => alerts.value.find(a => a.id === id && !a.acknowledged_at))
      if (open || (unlisted && (!reloaded || alertsHidden.value > 0))) ring()
      return
    }
    if (ids.some(id => !known.get(id).acknowledged_at)) ring()
  }

  function applyFireAlertUpdated(msg) {
    if (msg.resolved_at) { removeAlert(msg.id); return }
    upsertAlert(msg)
  }

  async function acknowledge(id) {
    try {
      // upsertAlert drops a row that came back resolved: the server answers 200 for an alert
      // that was resolved while the click was in flight.
      upsertAlert(await acknowledgeFireAlert(id))
    } catch (err) {
      // Resolved meanwhile (or deleted): nothing left to acknowledge, so it leaves the list.
      if (err?.status === 404) { removeAlert(id); return }
      throw err
    }
  }

  // Only what the operator could see is marked: an alert that arrived while the request was in
  // flight stays unacknowledged and keeps ringing.
  async function acknowledgeAll() {
    const ids = new Set(unacknowledged.value.map(a => a.id))
    await acknowledgeAllFireAlerts([...ids])
    const now = new Date().toISOString()
    alerts.value = alerts.value.map(a => (ids.has(a.id) && !a.acknowledged_at ? { ...a, acknowledged_at: now } : a))
  }

  // Logout: the next session starts from nothing. Bumping the sequence drops a load still in flight.
  function resetAlerts() {
    alertsSeq++
    alertsLog = []
    alerts.value = []
    ringToken.value = 0
    focusRequest.value = null
    alertsFailed.value = false
    alertsHidden.value = 0
    alertsLoadedOnce = false
    lastRingAt = -Infinity
    seen.clear()
    rang.clear()
  }

  return {
    hotspots, burntAreas, fetchedAt, upstreamState, burntFetchedAt, burntUpstreamState, layers, anyLayerOn,
    shownFetchedAt, shownUpstreamState, fetchFailed,
    fetchHotspots, fetchBurntAreas, refreshVisible, retryFailed, markFeedFailed, setLayer, applyFireDataUpdated,
    alerts, ringToken, alertsFailed, alertsHidden, unacknowledged, focusRequest, requestFocus, clearFocusRequest,
    zones, zonesFailed, upsertHotspotFeature, dismissHotspot, reportFire, extinguish, fetchZones, createZone, updateZone, disableZone, enableZone, applyFireZonesUpdated,
    fetchOpenAlerts, applyFireAlert, applyFireAlertRepeat, applyFireAlertUpdated, acknowledge, acknowledgeAll, resetAlerts,
  }
})
