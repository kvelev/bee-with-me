import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const loc  = { setConnected: vi.fn(), fetchLive: vi.fn(async () => {}), fetchTrail: vi.fn(async () => {}) }
const sos  = { fetchSOS: vi.fn(async () => {}), applySOSAlert: vi.fn() }
const fire = { retryFailed: vi.fn(async () => {}), refreshVisible: vi.fn(async () => {}), applyFireDataUpdated: vi.fn(async () => {}),
  applyFireZonesUpdated: vi.fn(async () => {}), fetchOpenAlerts: vi.fn(async () => {}), applyFireAlert: vi.fn(), applyFireAlertRepeat: vi.fn(async () => {}), applyFireAlertUpdated: vi.fn() }
const gateway = { applyStatus: vi.fn(), fetchStatus: vi.fn(async () => {}) }
vi.mock('../modules/gateway/store.js', () => ({ useGatewayStore: () => gateway }))
vi.mock('../modules/tracking/store.js', () => ({ useTrackingStore: () => loc }))
vi.mock('../modules/sos/store.js', () => ({ useSosStore: () => sos }))
vi.mock('../modules/fire/store.js', () => ({ useFireStore: () => fire }))
vi.mock('vue', async (orig) => ({ ...(await orig()), onUnmounted: vi.fn() }))

import { onUnmounted } from 'vue'
import { useWebSocket } from './useWebSocket'

describe('useWebSocket fire refetch', () => {
  let sockets
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    sockets = []
    globalThis.WebSocket = vi.fn(function () { sockets.push(this); this.close = vi.fn() })
  })
  afterEach(() => { vi.useRealTimers() })

  it('the 45 s resync tick does not refetch fire layers, a reconnect does [B33]', async () => {
    const { connect } = useWebSocket()
    connect()
    sockets[0].onopen()                       // first connect: nothing to catch up on
    await vi.advanceTimersByTimeAsync(45_000 * 3)
    expect(loc.fetchLive).toHaveBeenCalledTimes(3)
    expect(fire.refreshVisible).not.toHaveBeenCalled()

    sockets[0].onclose()                      // drop, then reconnect
    await vi.advanceTimersByTimeAsync(3_000)
    sockets[1].onopen()
    expect(fire.refreshVisible).toHaveBeenCalledTimes(1)
  })

  it('fire_data_updated applies the update [B33]', () => {
    const { connect } = useWebSocket()
    connect()
    sockets[sockets.length - 1].onmessage({ data: JSON.stringify({ type: 'fire_data_updated', fetched_at: null }) })
    expect(fire.applyFireDataUpdated).toHaveBeenCalledTimes(1)
  })

  it('fire_zones_updated refetches zones through the store [B52]', () => {
    const { connect } = useWebSocket()
    connect()
    sockets[sockets.length - 1].onmessage({ data: JSON.stringify({ type: 'fire_zones_updated' }) })
    expect(fire.applyFireZonesUpdated).toHaveBeenCalledTimes(1)
  })

  it('every resync tick retries failed fire feeds, also after the first connect [B35]', async () => {
    const { connect } = useWebSocket()
    connect()
    sockets[0].onopen()
    await vi.advanceTimersByTimeAsync(45_000 * 2)
    expect(loc.fetchLive).toHaveBeenCalled()
    expect(fire.retryFailed).toHaveBeenCalledTimes(loc.fetchLive.mock.calls.length)
  })

  it('fire alarm messages reach the store [T17]', () => {
    const { connect } = useWebSocket()
    connect()
    const send = (m) => sockets[sockets.length - 1].onmessage({ data: JSON.stringify(m) })
    send({ type: 'fire_alert', id: 'a1' })
    send({ type: 'fire_alert_repeat', alert_ids: ['a1'] })
    send({ type: 'fire_alert_updated', id: 'a1', acknowledged_at: 'x' })
    expect(fire.applyFireAlert).toHaveBeenCalledTimes(1)
    expect(fire.applyFireAlertRepeat).toHaveBeenCalledTimes(1)
    expect(fire.applyFireAlertUpdated).toHaveBeenCalledTimes(1)
  })

  it('every resync tick re-pulls the open fire alarms, a missed push must not hide one [T17]', async () => {
    const { connect } = useWebSocket()
    connect()
    sockets[0].onopen()
    await vi.advanceTimersByTimeAsync(45_000 * 2)
    expect(fire.fetchOpenAlerts).toHaveBeenCalledTimes(loc.fetchLive.mock.calls.length)
    expect(fire.fetchOpenAlerts).toHaveBeenCalled()
  })
  it('after disconnect() a late onclose schedules no reconnect and no resync [B58][B60]', async () => {
    const { connect, disconnect } = useWebSocket()
    connect()
    sockets[0].onopen()
    const originalOnclose = sockets[0].onclose   // what the browser would still call if it were not detached
    disconnect()
    vi.clearAllMocks()                        // drop the catch-up pull a reconnect onopen does
    originalOnclose()                         // the guard itself must hold, not only the detach
    await vi.advanceTimersByTimeAsync(3_000 + 45_000 * 2)
    expect(sockets).toHaveLength(1)
    expect(loc.fetchLive).not.toHaveBeenCalled()
  })

  it('connect() after disconnect() works again and leaves one live socket [B58][B60]', async () => {
    const { connect, disconnect } = useWebSocket()
    connect()
    const staleOnclose = sockets[0].onclose
    disconnect()
    connect()
    staleOnclose()                            // stale close from the first socket
    await vi.advanceTimersByTimeAsync(3_000)
    expect(sockets).toHaveLength(2)
    sockets[1].onclose()                      // unexpected drop still reconnects
    await vi.advanceTimersByTimeAsync(3_000)
    expect(sockets).toHaveLength(3)
  })

  it('a connect() from a view that already unmounted opens no socket and does not clear the stop [B60]', async () => {
    const { connect, disconnect } = useWebSocket()       // the view that mounted first
    const unmount = onUnmounted.mock.calls.at(-1)[0]
    connect()
    unmount()                                             // logout while its mount fetches are pending
    expect(sockets).toHaveLength(1)
    connect()                                             // the late connect() after the awaits
    expect(sockets).toHaveLength(1)                       // no orphan socket
    await vi.advanceTimersByTimeAsync(3_000 + 45_000 * 2)
    expect(loc.fetchLive).not.toHaveBeenCalled()          // no resync loop either
    disconnect()
  })

  it('a new view after the old one unmounted can still connect [B60]', () => {
    const old = useWebSocket()
    onUnmounted.mock.calls.at(-1)[0]()
    old.connect()
    expect(sockets).toHaveLength(0)
    const fresh = useWebSocket()
    fresh.connect()
    expect(sockets).toHaveLength(1)
    fresh.disconnect()
  })
})
