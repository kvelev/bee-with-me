import { beforeEach, describe, expect, it, vi } from 'vitest'

const fire = {
  retryFailed: vi.fn(async () => {}), refreshVisible: vi.fn(async () => {}), fetchOpenAlerts: vi.fn(async () => {}),
  applyFireDataUpdated: vi.fn(async () => {}), applyFireZonesUpdated: vi.fn(async () => {}), applyFireAlert: vi.fn(),
  applyFireAlertRepeat: vi.fn(async () => {}), applyFireAlertUpdated: vi.fn(),
}
vi.mock('./store.js', () => ({ useFireStore: () => fire }))

import { collectLiveHandlers, collectLiveHooks, dispatchLive } from '../../platform/live/dispatch.js'
import fireModule from './index.js'

const CASES = [
  ['fire_data_updated', 'applyFireDataUpdated'],
  ['fire_zones_updated', 'applyFireZonesUpdated'],
  ['fire_alert', 'applyFireAlert'],
  ['fire_alert_repeat', 'applyFireAlertRepeat'],
  ['fire_alert_updated', 'applyFireAlertUpdated'],
]

describe('fire live contributions', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('each of the five fire message types reaches its store action [T510]', () => {
    const handlers = collectLiveHandlers([fireModule])
    for (const [type, action] of CASES) {
      const msg = { type, id: 'a1' }
      dispatchLive(handlers, msg)
      expect(fire[action], type).toHaveBeenCalledTimes(1)
    }
    expect(fire.applyFireAlert).toHaveBeenCalledWith({ type: 'fire_alert', id: 'a1' })
  })

  it('a tick retries failed feeds and refetches the open alarms, and neither failure stops the other [T510]', async () => {
    const { onTick } = collectLiveHooks([fireModule])
    expect(onTick).toHaveLength(1)
    fire.retryFailed.mockRejectedValueOnce(new Error('feed down'))
    await expect(onTick[0]()).resolves.toBeDefined()
    expect(fire.retryFailed).toHaveBeenCalledTimes(1)
    expect(fire.fetchOpenAlerts).toHaveBeenCalledTimes(1)

    fire.fetchOpenAlerts.mockRejectedValueOnce(new Error('alerts down'))
    await expect(onTick[0]()).resolves.toBeDefined()
    expect(fire.retryFailed).toHaveBeenCalledTimes(2)
  })

  it('a reconnect refreshes the visible layers [T510]', async () => {
    const { onReconnect } = collectLiveHooks([fireModule])
    expect(onReconnect).toHaveLength(1)
    await onReconnect[0]()
    expect(fire.refreshVisible).toHaveBeenCalledTimes(1)
    expect(fire.retryFailed).not.toHaveBeenCalled()
  })
})
