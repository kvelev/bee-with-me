import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('../../api', () => ({
  getFireHotspots: vi.fn(), getFireBurntAreas: vi.fn(), getFireStatus: vi.fn(),
  getFireAlerts: vi.fn(), acknowledgeFireAlert: vi.fn(), acknowledgeAllFireAlerts: vi.fn(),
}))

import { getFireAlerts, acknowledgeFireAlert, acknowledgeAllFireAlerts } from '../../api'
import { useFireStore } from './store.js'

const alert = (id, extra = {}) => ({
  id, target_type: 'hq', device_id: null, full_name: null, distance_m: 1200,
  hotspot: { id: `h-${id}`, latitude: 42.5, longitude: 24.5, acquired_at: '2026-10-02T09:00:00+00:00', source: 'viirs' },
  triggered_at: '2026-10-02T10:00:00+00:00', acknowledged_at: null, resolved_at: null, resolve_reason: null, ...extra,
})

describe('fire alerts in useFireStore', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    vi.clearAllMocks()
    vi.useFakeTimers()
  })
  afterEach(() => { vi.useRealTimers() })

  it('a new alert is added once and rings once [T17]', () => {
    const store = useFireStore()
    store.applyFireAlert(alert('a1'))
    store.applyFireAlert(alert('a1'))
    expect(store.alerts).toHaveLength(1)
    expect(store.ringToken).toBe(1)
  })

  it('restoring after reload shows alerts without ringing [T17]', async () => {
    getFireAlerts.mockResolvedValue([alert('a1'), alert('a2', { acknowledged_at: '2026-10-02T10:01:00+00:00' })])
    const store = useFireStore()
    await store.fetchOpenAlerts()
    expect(getFireAlerts).toHaveBeenCalledWith({ state: 'open' })
    expect(store.alerts).toHaveLength(2)
    expect(store.unacknowledged.map(a => a.id)).toEqual(['a1'])
    expect(store.ringToken).toBe(0)
  })

  it('one repeat message rings once however many alerts it lists [T17]', () => {
    const store = useFireStore()
    store.applyFireAlert(alert('a1')); store.applyFireAlert(alert('a2'))
    vi.advanceTimersByTime(5000)   // past the ring coalescing window
    const before = store.ringToken
    store.applyFireAlertRepeat({ alert_ids: ['a1', 'a2'] })
    expect(store.ringToken).toBe(before + 1)
  })

  it('a repeat for acknowledged alerts only stays silent [T17]', () => {
    const store = useFireStore()
    store.applyFireAlert(alert('a1', { acknowledged_at: 'x' }))
    store.applyFireAlertRepeat({ alert_ids: ['a1'] })
    expect(store.ringToken).toBe(0)
  })

  it('a repeat for an unknown alert refetches and rings [T17]', async () => {
    getFireAlerts.mockResolvedValue([alert('a9')])
    const store = useFireStore()
    await store.applyFireAlertRepeat({ alert_ids: ['a9'] })
    expect(getFireAlerts).toHaveBeenCalled()
    expect(store.alerts.map(a => a.id)).toEqual(['a9'])
    expect(store.ringToken).toBe(1)
  })

  it('updates merge acknowledgement and remove resolved alerts [T17]', () => {
    const store = useFireStore()
    store.applyFireAlert(alert('a1'))
    store.applyFireAlertUpdated(alert('a1', { acknowledged_at: '2026-10-02T10:02:00+00:00' }))
    expect(store.unacknowledged).toHaveLength(0)
    expect(store.alerts).toHaveLength(1)
    store.applyFireAlertUpdated(alert('a1', { resolved_at: 'y', resolve_reason: 'aged_out' }))
    expect(store.alerts).toHaveLength(0)
  })

  it('acknowledge and acknowledge-all call the API and update state [T17]', async () => {
    const store = useFireStore()
    store.applyFireAlert(alert('a1')); store.applyFireAlert(alert('a2'))
    acknowledgeFireAlert.mockResolvedValue(alert('a1', { acknowledged_at: 'now' }))
    await store.acknowledge('a1')
    expect(acknowledgeFireAlert).toHaveBeenCalledWith('a1')
    expect(store.unacknowledged.map(a => a.id)).toEqual(['a2'])
    acknowledgeAllFireAlerts.mockResolvedValue({ acknowledged: 1 })
    await store.acknowledgeAll()
    expect(store.unacknowledged).toHaveLength(0)
  })

  it('a WebSocket envelope key is not kept and a late message cannot re-arm an alert [T17]', () => {
    const store = useFireStore()
    store.applyFireAlert({ ...alert('a1'), type: 'fire_alert' })
    expect(store.alerts[0].type).toBeUndefined()
    store.applyFireAlertUpdated(alert('a1', { acknowledged_at: 'x' }))
    store.applyFireAlertUpdated(alert('a1'))   // reordered older message
    expect(store.unacknowledged).toHaveLength(0)
  })

  it('a load that was in flight does not undo a newer push or acknowledgement [T17]', async () => {
    let release
    getFireAlerts.mockImplementationOnce(() => new Promise((r) => { release = r }))
    const store = useFireStore()
    store.applyFireAlert(alert('a1'))
    const load = store.fetchOpenAlerts()
    store.applyFireAlert(alert('a2'))                                       // pushed while loading
    store.applyFireAlertUpdated(alert('a1', { acknowledged_at: 'x' }))      // acknowledged elsewhere
    release([alert('a1')])                                                  // older snapshot: no a2, a1 open
    await load
    expect(store.alerts.map(a => a.id).sort()).toEqual(['a1', 'a2'])
    expect(store.unacknowledged.map(a => a.id)).toEqual(['a2'])
  })

  it('a failed load is flagged and cleared by the next good one [T17]', async () => {
    const store = useFireStore()
    getFireAlerts.mockRejectedValueOnce(new Error('down'))
    await expect(store.fetchOpenAlerts()).rejects.toThrow()
    expect(store.alertsFailed).toBe(true)
    getFireAlerts.mockResolvedValueOnce([])
    await store.fetchOpenAlerts()
    expect(store.alertsFailed).toBe(false)
  })

  it('acknowledge-all only marks what was listed when it was sent [T17]', async () => {
    const store = useFireStore()
    store.applyFireAlert(alert('a1'))
    let done
    acknowledgeAllFireAlerts.mockImplementationOnce(() => new Promise((r) => { done = r }))
    const p = store.acknowledgeAll()
    store.applyFireAlert(alert('a2'))   // arrives while the request is in flight
    done({ acknowledged: 1 })
    await p
    expect(store.unacknowledged.map(a => a.id)).toEqual(['a2'])
  })

  it('acknowledging an alert that was resolved meanwhile drops it quietly [T17]', async () => {
    const store = useFireStore()
    store.applyFireAlert(alert('a1'))
    // The API answers 200 with the resolved row, never 404.
    acknowledgeFireAlert.mockResolvedValue(alert('a1', { resolved_at: 'r', resolve_reason: 'out_of_range' }))
    await store.acknowledge('a1')
    expect(store.alerts).toHaveLength(0)
  })

  it('show on map sets one focus request that is cleared once used [T17]', () => {
    const store = useFireStore()
    store.requestFocus(42.5, 24.5)
    expect(store.focusRequest).toMatchObject({ latitude: 42.5, longitude: 24.5 })
    store.clearFocusRequest()
    expect(store.focusRequest).toBeNull()
  })
})
