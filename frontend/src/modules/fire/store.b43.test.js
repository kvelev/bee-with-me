import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('../../api', () => ({
  getFireHotspots: vi.fn(), getFireBurntAreas: vi.fn(), getFireStatus: vi.fn(),
  getFireAlerts: vi.fn(), acknowledgeFireAlert: vi.fn(), acknowledgeAllFireAlerts: vi.fn(),
  login: vi.fn(), getMe: vi.fn(),
}))

import { getFireAlerts, acknowledgeFireAlert, acknowledgeAllFireAlerts } from '../../api'
import { useFireStore } from './store.js'
import { useAuthStore } from '../../stores/auth'

const alert = (id, extra = {}) => ({
  id, target_type: 'hq', device_id: null, full_name: null, distance_m: 1200,
  hotspot: { id: `h-${id}`, latitude: 42.5, longitude: 24.5, acquired_at: '2026-10-02T09:00:00+00:00', source: 'viirs' },
  triggered_at: '2026-10-02T10:00:00+00:00', acknowledged_at: null, resolved_at: null, resolve_reason: null, ...extra,
})
const withTotal = (list, total) => Object.defineProperty([...list], 'total', { value: total })

describe('fire alarms: B43', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    vi.clearAllMocks()
    vi.useFakeTimers()
  })
  afterEach(() => { vi.useRealTimers() })

  it('an alert learned from a resync rings once, the first load stays silent [B43]', async () => {
    const store = useFireStore()
    getFireAlerts.mockResolvedValue([alert('a1')])
    await store.fetchOpenAlerts()
    expect(store.ringToken).toBe(0)
    getFireAlerts.mockResolvedValue([alert('a1'), alert('a2')])
    await store.fetchOpenAlerts()
    expect(store.ringToken).toBe(1)
    await store.fetchOpenAlerts()          // nothing new: quiet
    expect(store.ringToken).toBe(1)
  })

  it('a push after the fetch already delivered the alert does not ring twice, the reverse order neither [B43]', async () => {
    const store = useFireStore()
    getFireAlerts.mockResolvedValue([])
    await store.fetchOpenAlerts()
    getFireAlerts.mockResolvedValue([alert('a2')])
    await store.fetchOpenAlerts()
    expect(store.ringToken).toBe(1)
    vi.advanceTimersByTime(5000)
    store.applyFireAlert(alert('a2'))
    expect(store.ringToken).toBe(1)
    vi.advanceTimersByTime(5000)
    store.applyFireAlert(alert('a3'))
    expect(store.ringToken).toBe(2)
    vi.advanceTimersByTime(5000)
    getFireAlerts.mockResolvedValue([alert('a2'), alert('a3')])
    await store.fetchOpenAlerts()
    expect(store.ringToken).toBe(2)
  })

  it('a push after a first load that already listed the alert still rings once [B43]', async () => {
    const store = useFireStore()
    getFireAlerts.mockResolvedValue([alert('a2')])
    await store.fetchOpenAlerts()
    expect(store.ringToken).toBe(0)
    store.applyFireAlert(alert('a2'))      // the fetch beat the push: this is the first the operator hears
    expect(store.ringToken).toBe(1)
    vi.advanceTimersByTime(5000)
    store.applyFireAlert(alert('a2'))      // replayed push: quiet
    expect(store.ringToken).toBe(1)
  })

  it('acknowledging an alert that was resolved meanwhile does not bring it back [B43]', async () => {
    const store = useFireStore()
    store.applyFireAlert(alert('a1'))
    store.applyFireAlertUpdated(alert('a1', { resolved_at: 'r', resolve_reason: 'out_of_range' }))
    acknowledgeFireAlert.mockResolvedValue(alert('a1', { resolved_at: 'r', resolve_reason: 'out_of_range' }))
    await store.acknowledge('a1')
    expect(store.alerts).toHaveLength(0)
    expect(store.unacknowledged).toHaveLength(0)
  })

  it('a resolved row in the acknowledge response removes a listed alert [B43]', async () => {
    const store = useFireStore()
    store.applyFireAlert(alert('a1'))
    acknowledgeFireAlert.mockResolvedValue(alert('a1', { acknowledged_at: 'x', resolved_at: 'r' }))
    await store.acknowledge('a1')
    expect(store.alerts).toHaveLength(0)
  })

  it('20 alerts in one tick ring one tone, a later burst rings again [B43]', () => {
    const store = useFireStore()
    for (let i = 0; i < 20; i++) store.applyFireAlert(alert('c' + i))
    expect(store.ringToken).toBe(1)
    vi.advanceTimersByTime(2000)
    store.applyFireAlert(alert('later'))
    expect(store.ringToken).toBe(2)
  })

  it('reports how many open alerts the server holds beyond the loaded ones [B43]', async () => {
    const store = useFireStore()
    getFireAlerts.mockResolvedValue(withTotal([alert('a1'), alert('a2')], 502))
    await store.fetchOpenAlerts()
    expect(store.alertsHidden).toBe(500)
    getFireAlerts.mockResolvedValue([alert('a1')])
    await store.fetchOpenAlerts()
    expect(store.alertsHidden).toBe(0)
  })

  it('acknowledge-all sends the visible unacknowledged ids only [B43]', async () => {
    const store = useFireStore()
    store.applyFireAlert(alert('a1')); store.applyFireAlert(alert('a2'))
    store.applyFireAlert(alert('a3', { acknowledged_at: 'x' }))
    acknowledgeAllFireAlerts.mockResolvedValue({ acknowledged: 2 })
    await store.acknowledgeAll()
    expect(acknowledgeAllFireAlerts).toHaveBeenCalledWith(['a1', 'a2'])
  })

  it('logout clears alarm state and drops a load still in flight [B43]', async () => {
    const fire = useFireStore()
    const auth = useAuthStore()
    let release
    getFireAlerts.mockImplementationOnce(() => new Promise((r) => { release = r }))
    fire.applyFireAlert(alert('a1'))
    fire.requestFocus(42, 24)
    const load = fire.fetchOpenAlerts()
    auth.logout()
    expect(fire.alerts).toHaveLength(0)
    expect(fire.ringToken).toBe(0)
    expect(fire.focusRequest).toBeNull()
    release([alert('a1'), alert('a2')])
    await load
    expect(fire.alerts).toHaveLength(0)
    // the next session restores silently again, and an id from the old session is not "already told"
    getFireAlerts.mockResolvedValue([alert('a1')])
    await fire.fetchOpenAlerts()
    expect(fire.ringToken).toBe(0)
    vi.advanceTimersByTime(5000)
    fire.applyFireAlert(alert('a9'))
    expect(fire.ringToken).toBe(1)
  })
})
