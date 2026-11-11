import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../../api', () => ({
  getLivePositions: vi.fn(), getTrail: vi.fn(),
}))

import { getLivePositions } from '../../api'
import { useTrackingStore } from './store.js'

const row = (over = {}) => ({
  device_id: 'dA', user_id: 'u1', full_name: 'Ivan Petrov', latitude: 42.0, longitude: 23.0,
  received_at: new Date().toISOString(), sos_active: false, ...over,
})
const msg = (over = {}) => ({
  type: 'location_update', device_id: 'dA', user_id: 'u1', latitude: 42.5, longitude: 23.5,
  gnss_valid: true, recorded_at: '2026-11-11T10:00:00Z', received_at: new Date().toISOString(), ...over,
})

describe('tracking store: hook isolation and removal', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    vi.mocked(getLivePositions).mockReset()
    vi.restoreAllMocks()
  })

  it('an update hook that throws is logged; the other hooks and the merge still happen [B100]', async () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    getLivePositions.mockResolvedValue([row()])
    const store = useTrackingStore()
    await store.fetchLive()
    store.addUpdateHook(() => { throw new Error('hook boom') })
    store.addUpdateHook((d) => ({ ...d, tagged: true }))
    expect(() => store.applyLocationUpdate(msg())).not.toThrow()
    expect(store.positions.dA).toMatchObject({ latitude: 42.5, tagged: true, full_name: 'Ivan Petrov' })
    expect(store.trails.dA).toHaveLength(1)
    expect(err).toHaveBeenCalledTimes(1)
    expect(JSON.stringify(err.mock.calls)).toContain('hook boom')
  })

  it('a removed device stays removed when an older /live answer lacks it [T590]', async () => {
    getLivePositions.mockResolvedValueOnce([row()])
    const store = useTrackingStore()
    await store.fetchLive()

    let resolve
    getLivePositions.mockReturnValueOnce(new Promise((r) => { resolve = r }))
    const inFlight = store.fetchLive()
    store.applyLocationUpdate(msg())        // live message newer than the request
    store.removePosition('dA')              // the device is deleted
    resolve([])                              // the answer, started before, does not know it
    await inFlight

    expect('dA' in store.positions).toBe(false)
    expect(store.positionList.every(Boolean)).toBe(true)
    expect(store.positionList).toHaveLength(0)
  })

  it('a device re-added after removal is not shadowed by its old live tick [T590]', async () => {
    getLivePositions.mockResolvedValueOnce([row()])
    const store = useTrackingStore()
    await store.fetchLive()
    store.applyLocationUpdate(msg({ extra_field: 'old' }))
    store.removePosition('dA')

    getLivePositions.mockResolvedValueOnce([row({ latitude: 40.0, extra_field: 'fresh' })])
    await store.fetchLive()
    expect(store.positions.dA).toMatchObject({ latitude: 40.0, extra_field: 'fresh' })
  })
})
