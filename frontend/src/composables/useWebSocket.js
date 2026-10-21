import { onUnmounted } from 'vue'
import { useLocationsStore } from '../stores/locations'
import { useFireStore } from '../stores/fire'

// Belt-and-braces reconciliation. The WebSocket can look healthy and still be delivering
// nothing (a half-open socket after a sleep/wake, a dead LISTEN connection on the server),
// and a silent map is indistinguishable from a quiet one. Re-pulling the authoritative
// snapshot on a timer means every failure mode self-heals within a minute.
const RESYNC_INTERVAL_MS = 45_000
const RECONNECT_DELAY_MS = 3_000

let socket = null
let reconnectTimer = null
let resyncTimer = null
let hasConnectedBefore = false
// Set by connect({ catchUp: true }) when the view's first snapshot fetch failed (backend still
// starting). The first socket that really opens then pulls the snapshot like a reconnect would.
let catchUpOnOpen = false
// Set by an explicit disconnect() (logout, unmount); only the next connect() clears it.
let stopped = false

export function useWebSocket() {
  const store = useLocationsStore()
  const fireStore = useFireStore()
  // Per instance (one per view): set when this view unmounts. A connect() that arrives later (a mount
  // fetch that finished after logout) must neither open a socket nor clear the module-level `stopped`.
  let isUnmounted = false

  async function resync() {
    try {
      await Promise.all([store.fetchLive(), store.fetchSOS(), store.fetchTrail()])
    } catch { /* offline or backend restarting — the next tick tries again */ }
    // Fire layers are not re-pulled here (the backend polls EFFIS every 30 min), but a shown
    // feed whose last fetch failed is retried on every tick so it recovers by itself.
    fireStore.retryFailed().catch(() => { /* fetchFailed drives the pill */ })
    // Open fire alarms ARE re-pulled on every tick: a missed push must not hide an alarm (BP-02).
    fireStore.fetchOpenAlerts().catch(() => { /* alertsFailed drives the banner notice */ })
  }

  function detach(sock) {
    if (!sock) return
    sock.onopen = sock.onmessage = sock.onclose = sock.onerror = null
  }

  function connect({ catchUp = false } = {}) {
    if (isUnmounted) return
    // The reconnect timer calls connect() without options and must not clear a pending catch-up.
    if (catchUp) catchUpOnOpen = true
    stopped = false
    clearTimeout(reconnectTimer)
    // A quick re-login must not leave the previous socket alive next to the new one.
    const previous = socket
    detach(previous)
    previous?.close()
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const sock = new WebSocket(`${proto}://${location.host}/ws`)
    socket = sock

    sock.onopen = () => {
      store.setConnected(true)
      if (hasConnectedBefore || catchUpOnOpen) {
        // Reconnected after a drop (sleep/wake, network blip, backend restart) — any
        // pushes missed during the gap are gone, so pull a fresh snapshot instead of
        // trusting stale/partial state.
        resync()   // includes the open fire alarms
        // Fire layers refetch here, on `fire_data_updated` and on layer toggle, but not on the
        // 45 s resync tick: the backend polls EFFIS every 30 min, and the tick would re-pull
        // every hotspot and burnt-area polygon 40 times per poll.
        fireStore.refreshVisible().catch(() => { /* fetchFailed drives the pill */ })
      }
      hasConnectedBefore = true
      catchUpOnOpen = false
    }

    sock.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      if (msg.type === 'location_update') store.applyLocationUpdate(msg)
      if (msg.type === 'sos_alert')       store.applySOSAlert(msg)
      if (msg.type === 'serial_status')   store.applySerialStatus(msg)
      if (msg.type === 'fire_data_updated') fireStore.applyFireDataUpdated(msg).catch(() => {})
      if (msg.type === 'fire_zones_updated') fireStore.applyFireZonesUpdated().catch(() => {})
      if (msg.type === 'fire_alert')         fireStore.applyFireAlert(msg)
      if (msg.type === 'fire_alert_repeat')  fireStore.applyFireAlertRepeat(msg).catch(() => {})
      if (msg.type === 'fire_alert_updated') fireStore.applyFireAlertUpdated(msg)
    }

    sock.onclose = () => {
      if (stopped || socket !== sock) return
      store.setConnected(false)
      reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS)
    }

    sock.onerror = () => sock.close()

    clearInterval(resyncTimer)
    resyncTimer = setInterval(resync, RESYNC_INTERVAL_MS)
  }

  function disconnect() {
    stopped = true
    clearTimeout(reconnectTimer)
    clearInterval(resyncTimer)
    store.setConnected(false)
    detach(socket)
    socket?.close()
  }

  onUnmounted(() => {
    isUnmounted = true
    disconnect()
  })

  return { connect, disconnect, resync }
}
