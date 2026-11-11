import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../../api', () => ({
  getLivePositions: vi.fn(), getTrail: vi.fn(), getOpenSOS: vi.fn(), resolveSOS: vi.fn(),
}))

import { getLivePositions } from '../../api'
import { useTrackingStore } from './store.js'
import { useSosStore } from '../sos/store.js'

// The 15 keys of a thin location_update (plan section 1.4)
const thin = (over = {}) => ({
  type: 'location_update', device_id: 'dB', user_id: 'u2', mgrs: '34TFN1234567890',
  latitude: 42.1, longitude: 23.1, altitude_m: 500, speed_knots: 0, course_deg: 0,
  battery_voltage: 3.9, gnss_satellites: 8, gnss_valid: true, sos_active: false, repeater_mode: false,
  recorded_at: '2026-11-11T10:00:00Z', received_at: new Date().toISOString(), ...over,
})

const liveRow = (over = {}) => ({
  device_id: 'dA', user_id: 'u1', full_name: 'Ivan Petrov', rank: 'Captain', photo_url: '/p/ivan.jpg',
  groups: [{ id: 't1', name: 'Alpha' }], latitude: 42.0, longitude: 23.0,
  received_at: new Date().toISOString(), sos_active: false, ...over,
})

function deferred() {
  let resolve, reject
  const promise = new Promise((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}
const flush = () => new Promise(r => setTimeout(r, 0))

describe('tracking store with thin messages', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    vi.mocked(getLivePositions).mockReset()
  })

  it('a thin update keeps the name, the photo and the teams of a known device [T546]', async () => {
    getLivePositions.mockResolvedValue([liveRow()])
    const store = useTrackingStore()
    await store.fetchLive()
    store.applyLocationUpdate(thin({ device_id: 'dA', user_id: 'u1', latitude: 42.5 }))
    const row = store.positions.dA
    expect(row).toMatchObject({ full_name: 'Ivan Petrov', rank: 'Captain', photo_url: '/p/ivan.jpg', latitude: 42.5 })
    expect(row.groups).toEqual([{ id: 't1', name: 'Alpha' }])
    expect(getLivePositions).toHaveBeenCalledTimes(1)
  })

  it('an unknown device triggers one refetch for a burst of frames [T546]', async () => {
    const d = deferred()
    getLivePositions.mockReturnValue(d.promise)
    const store = useTrackingStore()
    store.applyLocationUpdate(thin())
    store.applyLocationUpdate(thin({ latitude: 42.2 }))
    store.applyLocationUpdate(thin({ latitude: 42.3 }))
    expect(getLivePositions.mock.calls.length).toBeLessThanOrEqual(2)
    expect(getLivePositions).toHaveBeenCalledTimes(1)
    d.resolve([liveRow({ device_id: 'dB', user_id: 'u2', full_name: 'Maria' })])
    await flush()
    expect(store.positions.dB.full_name).toBe('Maria')
    expect(getLivePositions.mock.calls.length).toBeLessThanOrEqual(2)
  })

  it('a changed user_id triggers a refetch [T546]', async () => {
    getLivePositions.mockResolvedValue([liveRow({ device_id: 'dB', user_id: 'u2', full_name: 'Maria' })])
    const store = useTrackingStore()
    store.positions.dB = liveRow({ device_id: 'dB', user_id: 'u1', full_name: 'Old Name' })
    store.applyLocationUpdate(thin({ user_id: 'u2' }))
    await flush()
    expect(getLivePositions).toHaveBeenCalledTimes(1)
    expect(store.positions.dB.full_name).toBe('Maria')
  })

  it('a failed refetch leaves the marker and does not throw [T546]', async () => {
    getLivePositions.mockRejectedValue(new Error('offline'))
    const store = useTrackingStore()
    expect(() => store.applyLocationUpdate(thin())).not.toThrow()
    await flush()
    expect(getLivePositions).toHaveBeenCalled()
    expect(store.positions.dB).toMatchObject({ device_id: 'dB', latitude: 42.1 })
  })

  it('a full message still works and asks for nothing [T546]', async () => {
    getLivePositions.mockResolvedValue([liveRow()])
    const store = useTrackingStore()
    await store.fetchLive()
    getLivePositions.mockClear()
    store.applyLocationUpdate({ ...thin({ device_id: 'dA', user_id: 'u1' }), full_name: 'Renamed', rank: 'Major', phone: '1', groups: [] })
    await flush()
    expect(getLivePositions).not.toHaveBeenCalled()
    expect(store.positions.dA).toMatchObject({ full_name: 'Renamed', rank: 'Major', phone: '1' })
  })

  it('an answer that started before a new device\'s first frame does not remove that device [T546]', async () => {
    const d = deferred()
    getLivePositions.mockReturnValueOnce(d.promise)
    const store = useTrackingStore()
    store.positions.dOld = liveRow({ device_id: 'dOld', full_name: 'Gone' })
    const pending = store.fetchLive()
    store.applyLocationUpdate(thin({ device_id: 'dB' }))
    d.resolve([liveRow({ device_id: 'dA' })])
    await pending
    expect(store.positions.dB).toBeDefined()
    expect(store.positions.dA).toBeDefined()
    // no newer live message: dropped as today
    expect(store.positions.dOld).toBeUndefined()
  })

  it('the kept row takes the name from the answer when the answer has the device [T546]', async () => {
    const d = deferred()
    getLivePositions.mockReturnValueOnce(d.promise)
    const store = useTrackingStore()
    const pending = store.fetchLive()
    store.applyLocationUpdate(thin({ latitude: 43.3 }))
    d.resolve([liveRow({ device_id: 'dB', user_id: 'u2', full_name: 'Maria', latitude: 41.0 })])
    await pending
    expect(store.positions.dB).toMatchObject({ full_name: 'Maria', latitude: 43.3 })
  })

  it('the SOS toast of a thin update uses the name of the row [T546]', async () => {
    getLivePositions.mockResolvedValue([liveRow()])
    const tracking = useTrackingStore()
    const sos = useSosStore()
    await tracking.fetchLive()
    tracking.applyLocationUpdate(thin({ device_id: 'dA', user_id: 'u1', sos_active: true }))
    expect(sos.sosNotifications).toHaveLength(1)
    expect(sos.sosNotifications[0].name).toBe('Ivan Petrov')
  })

  it('B2: a later thin message does not bring the old name back over the answer [T546]', async () => {
    const d = deferred()
    getLivePositions.mockReturnValueOnce(d.promise).mockResolvedValue([])
    const store = useTrackingStore()
    store.positions.dB = liveRow({ device_id: 'dB', user_id: 'u1', full_name: 'Old Name', rank: 'Private', photo_url: '/old.jpg' })
    store.applyLocationUpdate(thin({ user_id: 'u2' }))      // M1 starts F1
    store.applyLocationUpdate(thin({ user_id: 'u2', latitude: 43.3 }))   // M2 while F1 is in flight
    d.resolve([liveRow({ device_id: 'dB', user_id: 'u2', full_name: 'Maria', rank: 'Major', photo_url: '/m.jpg', latitude: 41.0 })])
    await flush()
    expect(store.positions.dB).toMatchObject({ full_name: 'Maria', rank: 'Major', photo_url: '/m.jpg', latitude: 43.3 })
  })

  it('B2: a name a full message carried while the request was in flight still wins [T546]', async () => {
    const d = deferred()
    getLivePositions.mockReturnValueOnce(d.promise)
    const store = useTrackingStore()
    const pending = store.fetchLive()
    store.applyLocationUpdate({ ...thin({ device_id: 'dA', user_id: 'u1' }), full_name: 'Renamed' })
    d.resolve([liveRow({ device_id: 'dA', full_name: 'Ivan Petrov', rank: 'Captain' })])
    await pending
    expect(store.positions.dA).toMatchObject({ full_name: 'Renamed', rank: 'Captain' })
  })
})
