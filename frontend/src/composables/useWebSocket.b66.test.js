import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const loc  = { setConnected: vi.fn(), fetchLive: vi.fn(async () => {}), fetchSOS: vi.fn(async () => {}), fetchTrail: vi.fn(async () => {}) }
const fire = { retryFailed: vi.fn(async () => {}), refreshVisible: vi.fn(async () => {}), applyFireDataUpdated: vi.fn(async () => {}),
  applyFireZonesUpdated: vi.fn(async () => {}), fetchOpenAlerts: vi.fn(async () => {}), applyFireAlert: vi.fn(), applyFireAlertRepeat: vi.fn(async () => {}), applyFireAlertUpdated: vi.fn() }
vi.mock('../stores/locations', () => ({ useLocationsStore: () => loc }))
vi.mock('../stores/fire', () => ({ useFireStore: () => fire }))
vi.mock('vue', async (orig) => ({ ...(await orig()), onUnmounted: vi.fn() }))

describe('useWebSocket catch-up after a failed first snapshot', () => {
  let sockets
  let useWebSocket
  beforeEach(async () => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    // hasConnectedBefore is module state: every test starts as a fresh page load.
    vi.resetModules()
    ;({ useWebSocket } = await import('./useWebSocket'))
    sockets = []
    globalThis.WebSocket = vi.fn(function () { sockets.push(this); this.close = vi.fn() })
  })
  afterEach(() => { vi.useRealTimers() })

  it('the first open after connect({ catchUp: true }) pulls a snapshot and refetches fire layers [B66]', async () => {
    const ws = useWebSocket()
    ws.connect({ catchUp: true })
    sockets[0].onopen()
    await vi.advanceTimersByTimeAsync(0)      // resync() pulls the open alarms after the snapshot settles
    expect(loc.fetchLive).toHaveBeenCalledTimes(1)
    expect(loc.fetchSOS).toHaveBeenCalledTimes(1)
    expect(loc.fetchTrail).toHaveBeenCalledTimes(1)
    expect(fire.fetchOpenAlerts).toHaveBeenCalledTimes(1)
    expect(fire.refreshVisible).toHaveBeenCalledTimes(1)
    ws.disconnect()
  })

  it('the first open without catchUp does not double-fetch [B66]', () => {
    const ws = useWebSocket()
    ws.connect()
    sockets[0].onopen()
    expect(loc.fetchLive).not.toHaveBeenCalled()
    expect(fire.refreshVisible).not.toHaveBeenCalled()
    ws.disconnect()
  })

  it('catch-up waits for the first socket that really opens and happens once [B66]', async () => {
    const ws = useWebSocket()
    ws.connect({ catchUp: true })
    sockets[0].onclose()                      // backend still down: refused, no open ever happened
    await vi.advanceTimersByTimeAsync(3_000)
    expect(loc.fetchLive).not.toHaveBeenCalled()
    sockets[1].onopen()                       // backend is up now
    expect(loc.fetchLive).toHaveBeenCalledTimes(1)
    expect(fire.refreshVisible).toHaveBeenCalledTimes(1)
    sockets[1].onclose()                      // a later drop is the ordinary reconnect catch-up
    await vi.advanceTimersByTimeAsync(3_000)
    sockets[2].onopen()
    expect(loc.fetchLive).toHaveBeenCalledTimes(2)
    ws.disconnect()
  })
})
