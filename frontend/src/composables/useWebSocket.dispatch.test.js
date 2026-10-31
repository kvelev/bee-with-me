import { describe, it, expect, vi, beforeEach } from 'vitest'

const loc = {
  setConnected: vi.fn(), fetchLive: vi.fn(async () => {}), fetchSOS: vi.fn(async () => {}), fetchTrail: vi.fn(async () => {}),
  applyLocationUpdate: vi.fn(), applySOSAlert: vi.fn(), applySerialStatus: vi.fn(),
}
const fire = {
  retryFailed: vi.fn(async () => {}), refreshVisible: vi.fn(async () => {}), fetchOpenAlerts: vi.fn(async () => {}),
  applyFireDataUpdated: vi.fn(async () => {}), applyFireZonesUpdated: vi.fn(async () => {}), applyFireAlert: vi.fn(),
  applyFireAlertRepeat: vi.fn(async () => {}), applyFireAlertUpdated: vi.fn(),
}
vi.mock('../stores/locations', () => ({ useLocationsStore: () => loc }))
vi.mock('../stores/fire', () => ({ useFireStore: () => fire }))
vi.mock('vue', async (orig) => ({ ...(await orig()), onUnmounted: vi.fn() }))

import { useWebSocket } from './useWebSocket'

const ALL = [
  ['location_update', loc, 'applyLocationUpdate'],
  ['sos_alert', loc, 'applySOSAlert'],
  ['serial_status', loc, 'applySerialStatus'],
  ['fire_data_updated', fire, 'applyFireDataUpdated'],
  ['fire_zones_updated', fire, 'applyFireZonesUpdated'],
  ['fire_alert', fire, 'applyFireAlert'],
  ['fire_alert_repeat', fire, 'applyFireAlertRepeat'],
  ['fire_alert_updated', fire, 'applyFireAlertUpdated'],
]

describe('useWebSocket message dispatch', () => {
  let sockets
  beforeEach(() => {
    vi.clearAllMocks()
    sockets = []
    globalThis.WebSocket = vi.fn(function () { sockets.push(this); this.close = vi.fn() })
  })

  function send(msg) {
    const { connect, disconnect } = useWebSocket()
    connect()
    sockets[sockets.length - 1].onmessage({ data: JSON.stringify(msg) })
    return disconnect
  }

  it.each(ALL)('dispatches %s to its store method [T117]', (type, store, method) => {
    const msg = { type, device_id: 'd1', marker: type }
    const disconnect = send(msg)
    expect(store[method]).toHaveBeenCalledTimes(1)
    const [arg] = store[method].mock.calls[0]
    if (method !== 'applyFireZonesUpdated') expect(arg).toEqual(msg)
    // no other dispatch target received the message
    for (const [, s, m] of ALL) if (!(s === store && m === method)) expect(s[m]).not.toHaveBeenCalled()
    disconnect()
  })

  it('ignores a message of an unknown type [T117]', () => {
    const disconnect = send({ type: 'nonsense' })
    for (const [, s, m] of ALL) expect(s[m]).not.toHaveBeenCalled()
    disconnect()
  })
})
