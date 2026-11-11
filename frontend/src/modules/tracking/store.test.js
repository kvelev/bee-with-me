import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../../api', () => ({ getLivePositions: vi.fn(), getTrail: vi.fn() }))

import { useTrackingStore } from './store.js'

const frame = (over = {}) => ({
  type: 'location_update', device_id: 'd1', full_name: 'Ivan', latitude: 42.1, longitude: 23.1,
  received_at: new Date().toISOString(), sos_active: false, ...over,
})

describe('tracking store', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('an update hook can change the message before it is merged [T544]', () => {
    const store = useTrackingStore()
    const seen = []
    store.addUpdateHook((data, existing) => { seen.push(existing); return { ...data, full_name: 'Hooked' } })
    store.addUpdateHook((data) => ({ ...data, phone: '123' }))
    store.applyLocationUpdate(frame())
    expect(seen).toEqual([{}])
    expect(store.positions.d1.full_name).toBe('Hooked')
    expect(store.positions.d1.phone).toBe('123')
    store.applyLocationUpdate(frame())
    expect(seen[1].full_name).toBe('Hooked')
  })

  it('patchPosition changes one field and keeps the rest [T544]', () => {
    const store = useTrackingStore()
    store.applyLocationUpdate(frame({ sos_active: true }))
    store.patchPosition('d1', { sos_active: false })
    expect(store.positions.d1).toMatchObject({ device_id: 'd1', full_name: 'Ivan', latitude: 42.1, sos_active: false })
    store.patchPosition('nobody', { sos_active: false })
    expect(store.positions.nobody).toBeUndefined()
  })

  it('removePosition drops the position and its trail [T544]', () => {
    const store = useTrackingStore()
    store.applyLocationUpdate(frame())
    store.applyLocationUpdate(frame({ device_id: 'd2' }))
    expect(store.trails.d1).toHaveLength(1)
    store.removePosition('d1')
    expect(store.positions.d1).toBeUndefined()
    expect(store.trails.d1).toBeUndefined()
    expect(store.positions.d2).toBeDefined()
  })
})
