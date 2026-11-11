import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('../../api', () => ({
  getFireHotspots: vi.fn(), getFireBurntAreas: vi.fn(), getFireStatus: vi.fn(),
  getFireAlerts: vi.fn(), acknowledgeFireAlert: vi.fn(), acknowledgeAllFireAlerts: vi.fn(),
  dismissFireHotspot: vi.fn(), createFieldReport: vi.fn(), extinguishFieldReport: vi.fn(),
  getSuppressionZones: vi.fn(), createSuppressionZone: vi.fn(), updateSuppressionZone: vi.fn(),
  disableSuppressionZone: vi.fn(), enableSuppressionZone: vi.fn(),
}))

import * as api from '../../api'
import { useFireStore } from './store.js'

const feature = (id, props = {}) => ({
  type: 'Feature', id, geometry: { type: 'Point', coordinates: [24.5, 42.5] },
  properties: { id, source: 'viirs', state: 'active', acquired_at: '2026-10-02T09:00:00+00:00', ...props },
})

describe('fire write actions', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('dismiss replaces the feature with the server copy [T19]', async () => {
    const store = useFireStore()
    store.hotspots = { type: 'FeatureCollection', features: [feature('h1'), feature('h2')] }
    api.dismissFireHotspot.mockResolvedValue(feature('h1', { state: 'dismissed', dismiss_notes: 'solar' }))
    await store.dismissHotspot('h1', 'solar')
    expect(api.dismissFireHotspot).toHaveBeenCalledWith('h1', 'solar')
    expect(store.hotspots.features.map(f => f.properties.state)).toEqual(['dismissed', 'active'])
  })

  it('reportFire sends device_id OR coordinates, never both [T19]', async () => {
    const store = useFireStore()
    api.createFieldReport.mockResolvedValue(feature('r1', { source: 'field_report' }))
    await store.reportFire({ deviceId: 'd1', latitude: 1, longitude: 2, notes: 'smoke' })
    expect(api.createFieldReport).toHaveBeenLastCalledWith({ device_id: 'd1', notes: 'smoke' })
    await store.reportFire({ latitude: 42.5, longitude: 24.5 })
    expect(api.createFieldReport).toHaveBeenLastCalledWith({ latitude: 42.5, longitude: 24.5, notes: null })
    expect(store.hotspots.features.map(f => f.id)).toEqual(['r1'])
  })

  it('extinguish updates the feature in place [T19]', async () => {
    const store = useFireStore()
    store.hotspots = { type: 'FeatureCollection', features: [feature('r1', { source: 'field_report' })] }
    api.extinguishFieldReport.mockResolvedValue(feature('r1', { source: 'field_report', state: 'extinguished' }))
    await store.extinguish('r1')
    expect(store.hotspots.features[0].properties.state).toBe('extinguished')
  })

  it('zones: create, update, disable keep the list in sync [T19]', async () => {
    const store = useFireStore()
    const zone = { id: 'z1', label: 'Solar', latitude: 42.5, longitude: 24.5, radius_m: 1000, is_active: true }
    api.createSuppressionZone.mockResolvedValue(zone)
    await store.createZone({ label: 'Solar', latitude: 42.5, longitude: 24.5 })
    api.updateSuppressionZone.mockResolvedValue({ ...zone, radius_m: 800 })
    await store.updateZone('z1', { ...zone, radius_m: 800 })
    expect(store.zones[0].radius_m).toBe(800)
    api.disableSuppressionZone.mockResolvedValue({ ...zone, is_active: false })
    await store.disableZone('z1')
    expect(store.zones[0].is_active).toBe(false)
    api.getSuppressionZones.mockResolvedValue([zone])
    await store.fetchZones(true)
    expect(api.getSuppressionZones).toHaveBeenCalledWith({ include_disabled: true })
  })

  it('a failed write rejects and leaves the features untouched [T19]', async () => {
    const store = useFireStore()
    store.hotspots = { type: 'FeatureCollection', features: [feature('h1')] }
    api.dismissFireHotspot.mockRejectedValue(Object.assign(new Error('x'), { status: 500 }))
    await expect(store.dismissHotspot('h1', null)).rejects.toThrow()
    expect(store.hotspots.features[0].properties.state).toBe('active')
  })

  it('a failed zone load sets zonesFailed and keeps the list; a later success clears it [T19]', async () => {
    const store = useFireStore()
    const zone = { id: 'z1', label: 'Solar', latitude: 42.5, longitude: 24.5, radius_m: 1000, is_active: true }
    api.getSuppressionZones.mockResolvedValueOnce([zone])
    await store.fetchZones()
    api.getSuppressionZones.mockRejectedValueOnce(new Error('down'))
    await expect(store.fetchZones()).rejects.toThrow()
    expect(store.zonesFailed).toBe(true)
    expect(store.zones).toHaveLength(1)
    api.getSuppressionZones.mockResolvedValueOnce([zone])
    await store.fetchZones()
    expect(store.zonesFailed).toBe(false)
  })

  it('turning the zones layer on loads zones [T19]', async () => {
    const store = useFireStore()
    api.getSuppressionZones.mockResolvedValue([])
    await store.setLayer('zones', true)
    expect(api.getSuppressionZones).toHaveBeenCalledWith({ include_disabled: false })
  })

  it('zone activation passes the version and swaps in the server copy [B52]', async () => {
    const store = useFireStore()
    const zone = { id: 'z1', label: 'Solar', radius_m: 1000, is_active: true, updated_at: 'u1' }
    store.zones = [zone]
    api.disableSuppressionZone.mockResolvedValue({ ...zone, is_active: false, updated_at: 'u2' })
    await store.disableZone('z1', 'u1')
    expect(api.disableSuppressionZone).toHaveBeenCalledWith('z1', 'u1')
    expect(store.zones[0]).toMatchObject({ is_active: false, updated_at: 'u2' })
    api.enableSuppressionZone.mockResolvedValue({ ...zone, is_active: true, updated_at: 'u3' })
    await store.enableZone('z1', 'u2')
    expect(api.enableSuppressionZone).toHaveBeenCalledWith('z1', 'u2')
    expect(store.zones[0]).toMatchObject({ is_active: true, updated_at: 'u3' })
  })

  it('fire_zones_updated refetches the zone list the view asked for and the shown hotspots [B52]', async () => {
    const store = useFireStore()
    await store.fetchZones(true)
    store.layers = { burnt: false, hotspots: true, zones: false }
    api.getSuppressionZones.mockClear()
    api.getFireHotspots.mockResolvedValue({ type: 'FeatureCollection', features: [] })
    api.getSuppressionZones.mockResolvedValue([{ id: 'z9' }])
    await store.applyFireZonesUpdated()
    expect(api.getSuppressionZones).toHaveBeenCalledWith({ include_disabled: true })
    expect(api.getFireHotspots).toHaveBeenCalledTimes(1)
    expect(store.zones).toEqual([{ id: 'z9' }])
  })

  it('fire_zones_updated before any zone list was loaded fetches no zones [B52]', async () => {
    const store = useFireStore()
    await store.applyFireZonesUpdated()
    expect(api.getSuppressionZones).not.toHaveBeenCalled()
  })
})
