import { onUnmounted } from 'vue'
import { useLocationsStore } from '../stores/locations'

let socket = null
let reconnectTimer = null

export function useWebSocket() {
  const store = useLocationsStore()

  function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    socket = new WebSocket(`${proto}://${location.host}/ws`)

    socket.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      if (msg.type === 'location_update') store.applyLocationUpdate(msg)
      if (msg.type === 'sos_alert')       store.applySOSAlert(msg)
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
