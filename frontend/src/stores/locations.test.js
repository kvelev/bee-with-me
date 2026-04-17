import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useLocationsStore } from './locations'

// Mock API module
vi.mock('../api', () => ({
  getLivePositions: vi.fn(),
  getOpenSOS:       vi.fn(),
  resolveSOS:       vi.fn(),
}))

import { getLivePositions, getOpenSOS, resolveSOS } from '../api'

describe('useLocationsStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('starts empty', () => {
    const store = useLocationsStore()
    expect(store.positionList).toEqual([])
    expect(store.hasSOS).toBe(false)
  })

  it('fetchLive populates positions keyed by device_id', async () => {
    getLivePositions.mockResolvedValue([
      { device_id: 'dev-1', mgrs: '35TLF123', latitude: 42.1, longitude: 24.5 },
      { device_id: 'dev-2', mgrs: '35TLG456', latitude: 42.2, longitude: 24.6 },
    ])
    const store = useLocationsStore()
    await store.fetchLive()
    expect(store.positionList).toHaveLength(2)
    expect(store.positions['dev-1'].mgrs).toBe('35TLF123')
  })

  it('fetchSOS populates sosAlerts', async () => {
    getOpenSOS.mockResolvedValue([{ id: 'sos-1', device_id: 'dev-1', full_name: 'Alpha' }])
    const store = useLocationsStore()
    await store.fetchSOS()
    expect(store.hasSOS).toBe(true)
    expect(store.sosAlerts).toHaveLength(1)
  })

  it('applyLocationUpdate merges data into existing position', () => {
    const store = useLocationsStore()
    store.positions['dev-1'] = { device_id: 'dev-1', mgrs: 'OLD', battery_voltage: 3.8 }
    store.applyLocationUpdate({ device_id: 'dev-1', mgrs: 'NEW', latitude: 42.5 })
    expect(store.positions['dev-1'].mgrs).toBe('NEW')
    expect(store.positions['dev-1'].battery_voltage).toBe(3.8) // kept from existing
    expect(store.positions['dev-1'].latitude).toBe(42.5)
  })

  it('applyLocationUpdate adds new device if not present', () => {
    const store = useLocationsStore()
    store.applyLocationUpdate({ device_id: 'dev-new', mgrs: '35TLF999' })
    expect(store.positions['dev-new']).toBeDefined()
  })

  it('applySOSAlert adds alert once', () => {
    const store = useLocationsStore()
    const alert = { device_id: 'dev-1', id: 'sos-1' }
    store.applySOSAlert(alert)
    store.applySOSAlert(alert) // duplicate — should not add twice
    expect(store.sosAlerts).toHaveLength(1)
  })

  it('resolveSOS removes alert by id', async () => {
    resolveSOS.mockResolvedValue(undefined)
    const store = useLocationsStore()
    store.sosAlerts = [
      { id: 'sos-1', device_id: 'dev-1' },
      { id: 'sos-2', device_id: 'dev-2' },
    ]
    await store.resolveSOS('sos-1')
    expect(store.sosAlerts).toHaveLength(1)
    expect(store.sosAlerts[0].id).toBe('sos-2')
  })

  it('hasSOS is false after all alerts resolved', async () => {
    resolveSOS.mockResolvedValue(undefined)
    const store = useLocationsStore()
    store.sosAlerts = [{ id: 'sos-1', device_id: 'dev-1' }]
    await store.resolveSOS('sos-1')
    expect(store.hasSOS).toBe(false)
  })
})
