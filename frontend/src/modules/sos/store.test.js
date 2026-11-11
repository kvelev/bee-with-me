import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../../api', () => ({
  getLivePositions: vi.fn(), getTrail: vi.fn(), getOpenSOS: vi.fn(), resolveSOS: vi.fn(async () => ({})),
}))

import { collectLiveHandlers, collectLiveHooks, dispatchLive } from '../../platform/live/dispatch.js'
import { MODULES } from '../index.js'
import { useTrackingStore } from '../tracking/index.js'
import { useSosStore } from './store.js'

const frame = (over = {}) => ({
  type: 'location_update', device_id: 'd1', full_name: 'Ivan', dev_sn: 1001, latitude: 42.1, longitude: 23.1,
  received_at: new Date().toISOString(), sos_active: true, ...over,
})

function stores() {
  const tracking = useTrackingStore()
  const sos = useSosStore()
  return { tracking, sos }
}

describe('sos store', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('a rising SOS flag raises one toast and a second frame does not [T544]', () => {
    const { tracking, sos } = stores()
    tracking.applyLocationUpdate(frame())
    tracking.applyLocationUpdate(frame())
    expect(sos.sosNotifications).toHaveLength(1)
    expect(sos.sosNotifications[0]).toMatchObject({ device_id: 'd1', name: 'Ivan' })
    expect(tracking.positions.d1.sos_active).toBe(true)
  })

  it('a resolved alert clears the marker flag and the next asserting frame does not relight it [T544]', async () => {
    const { tracking, sos } = stores()
    tracking.applyLocationUpdate(frame())
    sos.applySOSAlert({ type: 'sos_alert', id: 'a1', device_id: 'd1' })
    await sos.resolveSOS('a1')
    expect(sos.sosAlerts).toEqual([])
    expect(tracking.positions.d1.sos_active).toBe(false)
    tracking.applyLocationUpdate(frame())
    expect(tracking.positions.d1.sos_active).toBe(false)
    expect(sos.sosNotifications).toHaveLength(1)
  })

  it('a device that clears SOS can raise a new alert later [T544]', async () => {
    const { tracking, sos } = stores()
    tracking.applyLocationUpdate(frame())
    sos.applySOSAlert({ type: 'sos_alert', id: 'a1', device_id: 'd1' })
    await sos.resolveSOS('a1')
    tracking.applyLocationUpdate(frame({ sos_active: false }))
    tracking.applyLocationUpdate(frame())
    expect(tracking.positions.d1.sos_active).toBe(true)
    expect(sos.sosNotifications).toHaveLength(2)
  })

  it('the sos hook is registered before the first live message [T544]', () => {
    setActivePinia(createPinia())
    const { setup } = collectLiveHooks(MODULES)
    setup.forEach((fn) => fn())
    dispatchLive(collectLiveHandlers(MODULES), frame())
    expect(useSosStore().sosNotifications).toHaveLength(1)
  })
})
