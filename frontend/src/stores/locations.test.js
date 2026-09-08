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

  it('applySOSAlert merges into an existing entry rather than dropping the alert id', () => {
    const store = useLocationsStore()
    // Seeded by an early push that lacked the id (the shape that made Resolve a no-op)
    store.applySOSAlert({ device_id: 'dev-1' })
    store.applySOSAlert({ device_id: 'dev-1', id: 'sos-1', full_name: 'Alpha', dev_sn: 42 })
    expect(store.sosAlerts).toHaveLength(1)
    expect(store.sosAlerts[0].id).toBe('sos-1')
    expect(store.sosAlerts[0].full_name).toBe('Alpha')
  })

  it('applySOSAlert strips the websocket envelope type', () => {
    const store = useLocationsStore()
    store.applySOSAlert({ type: 'sos_alert', device_id: 'dev-1', id: 'sos-1' })
    expect(store.sosAlerts[0]).not.toHaveProperty('type')
  })

  it('resolveSOS refuses an alert with no id instead of posting undefined', async () => {
    const store = useLocationsStore()
    await expect(store.resolveSOS(undefined)).rejects.toThrow(/no id/)
    expect(resolveSOS).not.toHaveBeenCalled()
  })

  it('a no-fix frame updates the marker but adds no trail point', () => {
    const store = useLocationsStore()
    store.applyLocationUpdate({
      device_id: 'dev-1', latitude: 42.1, longitude: 24.5,
      gnss_valid: true, received_at: new Date().toISOString(),
    })
    expect(store.trails['dev-1']).toHaveLength(1)

    // Same coordinates carried forward because the device lost its fix — recording this
    // would draw a leg the rescuer never walked.
    store.applyLocationUpdate({
      device_id: 'dev-1', latitude: 42.1, longitude: 24.5,
      gnss_valid: false, received_at: new Date().toISOString(),
    })
    expect(store.trails['dev-1']).toHaveLength(1)
    expect(store.positions['dev-1'].gnss_valid).toBe(false)
  })

  it('trail points carry the server clock for pruning and labels', () => {
    const store = useLocationsStore()
    store.applyLocationUpdate({
      device_id: 'dev-1', latitude: 42.1, longitude: 24.5, gnss_valid: true,
      recorded_at: '2020-01-01T00:00:00Z',            // device clock badly wrong
      received_at: '2026-09-08T12:00:00Z',
    })
    expect(store.trails['dev-1'][0].received_at).toBe('2026-09-08T12:00:00Z')
  })

  it('silentList and lostList classify by age', () => {
    const store = useLocationsStore()
    const ago = (ms) => new Date(Date.now() - ms).toISOString()
    store.positions = {
      'a': { device_id: 'a', received_at: ago(1000) },              // live
      'b': { device_id: 'b', received_at: ago(15 * 60_000) },       // stale
      'c': { device_id: 'c', received_at: ago(45 * 60_000) },       // lost
    }
    expect(store.silentList.map(p => p.device_id).sort()).toEqual(['b', 'c'])
    expect(store.lostList.map(p => p.device_id)).toEqual(['c'])
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
