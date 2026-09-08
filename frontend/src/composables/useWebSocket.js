import { onUnmounted } from 'vue'
import { useLocationsStore } from '../stores/locations'

let socket = null
let reconnectTimer = null
let hasConnectedBefore = false

export function useWebSocket() {
  const store = useLocationsStore()

  function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    socket = new WebSocket(`${proto}://${location.host}/ws`)

    socket.onopen = () => {
      if (hasConnectedBefore) {
        // Reconnected after a drop (sleep/wake, network blip, backend restart) — any
        // pushes missed during the gap are gone, so pull a fresh snapshot instead of
        // trusting stale/partial state.
        store.fetchLive().catch(() => {})
        store.fetchSOS().catch(() => {})
        store.fetchTrail().catch(() => {})
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
      reconnectTimer = setTimeout(connect, 3000)
    }

    socket.onerror = () => socket.close()
  }

  function disconnect() {
    clearTimeout(reconnectTimer)
    socket?.close()
  }

  onUnmounted(disconnect)

  return { connect, disconnect }
}
