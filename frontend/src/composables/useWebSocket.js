import { onUnmounted } from 'vue'
import { MODULES } from '../modules/index.js'
import { useTrackingStore } from '../modules/tracking/index.js'
import { collectLiveHandlers, collectLiveHooks, dispatchLive, runHooks, runSetup } from '../platform/live/dispatch.js'

// What a message, a tick and a reconnect do is read from the modules' contributions.
const handlers = collectLiveHandlers(MODULES)
const hooks = collectLiveHooks(MODULES)

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
// The modules' `setup` hooks run once, on the first connect() of the page.
let setupDone = false

export function useWebSocket() {
  const store = useTrackingStore()
  // Per instance (one per view): set when this view unmounts. A connect() that arrives later (a mount
  // fetch that finished after logout) must neither open a socket nor clear the module-level `stopped`.
  let isUnmounted = false

  function resync() {
    return runHooks(hooks.onTick)
  }

  function detach(sock) {
    if (!sock) return
    sock.onopen = sock.onmessage = sock.onclose = sock.onerror = null
  }

  function connect({ catchUp = false } = {}) {
    if (isUnmounted) return
    if (!setupDone) {
      setupDone = true
      runSetup(hooks.setup)
    }
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
        resync()
        // Hooks that run only on a reconnect (a module's `live.onReconnect`, e.g. the fire layers).
        runHooks(hooks.onReconnect)
      }
      hasConnectedBefore = true
      // Defensive: hasConnectedBefore already covers every later open; this just keeps the flag honest.
      catchUpOnOpen = false
    }

    sock.onmessage = (event) => {
      dispatchLive(handlers, JSON.parse(event.data))
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
