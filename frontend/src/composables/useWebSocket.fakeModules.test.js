// @vitest-environment node
// The socket composable wired to a FAKE module list (not the real MODULES): proves it reads the contributions.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const setConnected = vi.fn()
const calls = []
const fake = {
  name: 'fake',
  liveHandlers: { ping: (m) => calls.push(['ping', m.n]) },
  live: {
    setup: vi.fn(() => calls.push(['setup'])),
    onTick: vi.fn(async () => { calls.push(['tick']) }),
    onReconnect: vi.fn(async () => { calls.push(['reconnect']) }),
  },
}
vi.mock('../modules/index.js', () => ({ MODULES: [fake] }))
vi.mock('../modules/tracking/index.js', () => ({ useTrackingStore: () => ({ setConnected }) }))
vi.mock('vue', async (orig) => ({ ...(await orig()), onUnmounted: vi.fn() }))

let sockets
let useWebSocket

beforeEach(async () => {
  vi.resetModules()
  calls.length = 0
  vi.clearAllMocks()
  sockets = []
  globalThis.WebSocket = vi.fn(function () { sockets.push(this); this.close = vi.fn() })
  globalThis.location = { protocol: 'http:', host: 'h' }
  ;({ useWebSocket } = await import('./useWebSocket.js'))
})
afterEach(() => { vi.restoreAllMocks() })

describe('useWebSocket wired to a fake MODULES list', () => {
  it('a message reaches the fake module handler, setup runs once over two connects [T590]', () => {
    const ws = useWebSocket()
    ws.connect()
    ws.connect()
    sockets.at(-1).onmessage({ data: JSON.stringify({ type: 'ping', n: 7 }) })
    expect(calls.filter((c) => c[0] === 'setup')).toHaveLength(1)
    expect(calls).toContainEqual(['ping', 7])
    ws.disconnect()
  })

  it('resync runs the fake onTick, a second open runs onReconnect [T590]', async () => {
    const ws = useWebSocket()
    ws.connect()
    sockets.at(-1).onopen()
    expect(fake.live.onReconnect).not.toHaveBeenCalled()
    await ws.resync()
    expect(fake.live.onTick).toHaveBeenCalledTimes(1)
    sockets.at(-1).onopen()
    await Promise.resolve()
    expect(fake.live.onReconnect).toHaveBeenCalledTimes(1)
    ws.disconnect()
  })

  it('an async setup hook that rejects is logged and the socket still opens [B98]', async () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    fake.live.setup.mockImplementationOnce(() => Promise.reject(new Error('setup late')))
    const unhandled = vi.fn()
    process.on('unhandledRejection', unhandled)
    const ws = useWebSocket()
    ws.connect()
    await new Promise((r) => setTimeout(r, 10))
    process.off('unhandledRejection', unhandled)
    expect(unhandled).not.toHaveBeenCalled()
    expect(err.mock.calls.flat().join(' ')).toContain('setup late')
    expect(sockets).toHaveLength(1)
    ws.disconnect()
  })
})
