import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('../../api', () => ({
  getFireHotspots: vi.fn(), getFireBurntAreas: vi.fn(), getFireStatus: vi.fn(),
  getFireAlerts: vi.fn(), acknowledgeFireAlert: vi.fn(), acknowledgeAllFireAlerts: vi.fn(),
  login: vi.fn(), getMe: vi.fn(),
}))

import { getFireAlerts, acknowledgeAllFireAlerts } from '../../api'
import { useFireStore } from './store.js'

const alert = (id, extra = {}) => ({
  id, target_type: 'hq', device_id: null, full_name: null, distance_m: 1200,
  hotspot: { id: `h-${id}`, latitude: 42.5, longitude: 24.5, acquired_at: '2026-10-02T09:00:00+00:00', source: 'viirs' },
  triggered_at: '2026-10-02T10:00:00+00:00', acknowledged_at: null, resolved_at: null, resolve_reason: null, ...extra,
})
const withTotal = (list, total) => Object.defineProperty([...list], 'total', { value: total ?? list.length })

describe('fire alarms: B45', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    vi.clearAllMocks()
    vi.useFakeTimers()
  })
  afterEach(() => { vi.useRealTimers() })

  it('a backwards wall-clock step does not mute new alerts or repeats [B45]', async () => {
    const store = useFireStore()
    store.applyFireAlert(alert('a1'))
    expect(store.ringToken).toBe(1)
    vi.setSystemTime(Date.now() - 3600_000)      // operator or NTP corrects the clock back by an hour
    vi.advanceTimersByTime(5000)
    store.applyFireAlert(alert('a2'))
    expect(store.ringToken).toBe(2)
    vi.advanceTimersByTime(5 * 60_000)
    getFireAlerts.mockResolvedValue(withTotal([alert('a1'), alert('a2')]))
    await store.applyFireAlertRepeat({ alert_ids: ['a1', 'a2'] })
    expect(store.ringToken).toBe(3)
  })

  it('a repeat for an alert hidden beyond the row limit rings [B45]', async () => {
    const store = useFireStore()
    const visible = Array.from({ length: 500 }, (_, i) => alert(`v${i}`, { acknowledged_at: 'x' }))
    getFireAlerts.mockResolvedValue(withTotal(visible, 501))
    await store.fetchOpenAlerts()
    expect(store.alertsHidden).toBe(1)
    vi.advanceTimersByTime(5000)
    await store.applyFireAlertRepeat({ alert_ids: ['old'] })
    expect(store.ringToken).toBe(1)
  })

  it('a repeat for an unknown alert rings even when the reload fails [B45]', async () => {
    const store = useFireStore()
    getFireAlerts.mockResolvedValue(withTotal([]))
    await store.fetchOpenAlerts()
    getFireAlerts.mockRejectedValue(new Error('down'))
    await store.applyFireAlertRepeat({ alert_ids: ['x'] })
    expect(store.alertsFailed).toBe(true)
    expect(store.ringToken).toBe(1)
  })

  it('a repeat for an alert that a full reload shows resolved stays quiet [B45]', async () => {
    const store = useFireStore()
    getFireAlerts.mockResolvedValue(withTotal([]))
    await store.fetchOpenAlerts()
    await store.applyFireAlertRepeat({ alert_ids: ['gone'] })
    expect(store.ringToken).toBe(0)
  })

  it('a repeat for an acknowledged known alert stays quiet [B45]', async () => {
    const store = useFireStore()
    getFireAlerts.mockResolvedValue(withTotal([alert('k', { acknowledged_at: 'x' })]))
    await store.fetchOpenAlerts()
    await store.applyFireAlertRepeat({ alert_ids: ['k'] })
    expect(store.ringToken).toBe(0)
  })

  it('after a failed first load the next load rings for unacknowledged alerts [B45]', async () => {
    const store = useFireStore()
    getFireAlerts.mockRejectedValueOnce(new Error('down'))
    await store.fetchOpenAlerts().catch(() => {})
    getFireAlerts.mockResolvedValue(withTotal([alert('n1'), alert('n2', { acknowledged_at: 'x' })]))
    await store.fetchOpenAlerts()
    expect(store.ringToken).toBe(1)
    await store.fetchOpenAlerts()                // nothing new: quiet
    expect(store.ringToken).toBe(1)
  })

  it('a successful first load stays silent and a reload stays silent [B45]', async () => {
    const store = useFireStore()
    getFireAlerts.mockResolvedValue(withTotal([alert('a1')]))
    await store.fetchOpenAlerts()
    await store.fetchOpenAlerts()
    expect(store.ringToken).toBe(0)
  })

  it('a resync-only alert rings once, ack then a new alert rings again [B45]', async () => {
    const store = useFireStore()
    getFireAlerts.mockResolvedValue(withTotal([]))
    await store.fetchOpenAlerts()
    getFireAlerts.mockResolvedValue(withTotal([alert('r')]))
    await store.fetchOpenAlerts()
    expect(store.ringToken).toBe(1)
    vi.advanceTimersByTime(5000)
    store.applyFireAlert(alert('r'))
    expect(store.ringToken).toBe(1)
    acknowledgeAllFireAlerts.mockResolvedValue({ acknowledged: 1 })
    await store.acknowledgeAll()
    vi.advanceTimersByTime(5000)
    store.applyFireAlert(alert('q'))
    expect(store.ringToken).toBe(2)
  })
})
