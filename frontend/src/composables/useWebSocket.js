import { onUnmounted } from 'vue'
import { useLocationsStore } from '../stores/locations'

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

export function useWebSocket() {
  const store = useLocationsStore()

  async function resync() {
    try {
      await Promise.all([store.fetchLive(), store.fetchSOS(), store.fetchTrail()])
    } catch { /* offline or backend restarting — the next tick tries again */ }
  }

  function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    socket = new WebSocket(`${proto}://${location.host}/ws`)

    socket.onopen = () => {
      store.setConnected(true)
      if (hasConnectedBefore) {
        // Reconnected after a drop (sleep/wake, network blip, backend restart) — any
        // pushes missed during the gap are gone, so pull a fresh snapshot instead of
        // trusting stale/partial state.
        resync()
      }
      hasConnectedBefore = true
    }

    socket.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      if (msg.type === 'location_update') store.applyLocationUpdate(msg)
      if (msg.type === 'sos_alert')       store.applySOSAlert(msg)
      if (msg.type === 'serial_status')   store.applySerialStatus(msg)
    }

    socket.onclose = () => {
      store.setConnected(false)
      reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS)
    }

    socket.onerror = () => socket.close()

    clearInterval(resyncTimer)
    resyncTimer = setInterval(resync, RESYNC_INTERVAL_MS)
  }

  function disconnect() {
    clearTimeout(reconnectTimer)
    clearInterval(resyncTimer)
    store.setConnected(false)
    socket?.close()
  }

  onUnmounted(disconnect)

  return { connect, disconnect, resync }
}
