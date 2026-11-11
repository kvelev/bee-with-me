import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../../api', () => ({
  getLivePositions: vi.fn(), getTrail: vi.fn(), getOpenSOS: vi.fn(), resolveSOS: vi.fn(),
}))

import { getOpenSOS } from '../../api'
import { useTrackingStore } from '../tracking/index.js'
import { useSosStore } from './store.js'

// The 5 keys of a thin sos_alert (plan section 1.4)
const thinAlert = (over = {}) => ({
  type: 'sos_alert', id: 'a1', device_id: 'd1', user_id: 'u1', dev_sn: 1001,
  triggered_at: '2026-11-11T10:00:00Z', ...over,
})

function deferred() {
  let resolve, reject
  const promise = new Promise((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}
const flush = () => new Promise(r => setTimeout(r, 0))

function seeded() {
  const tracking = useTrackingStore()
  const sos = useSosStore()
  tracking.positions.d1 = {
    device_id: 'd1', user_id: 'u1', full_name: 'Ivan Petrov', rank: 'Captain', device_name: 'Bee 1', dev_sn: 1001,
    latitude: 42, longitude: 23, received_at: new Date().toISOString(), sos_active: true,
  }
  return { tracking, sos }
}

describe('sos store with thin messages', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    vi.mocked(getOpenSOS).mockReset()
  })

  it('a thin sos alert is shown at once and survives a failed refetch [T546]', async () => {
    getOpenSOS.mockRejectedValue(new Error('offline'))
    const { sos } = seeded()
    expect(() => sos.applySOSAlert(thinAlert())).not.toThrow()
    expect(sos.sosAlerts).toHaveLength(1)
    expect(sos.sosAlerts[0]).toMatchObject({ id: 'a1', full_name: 'Ivan Petrov', rank: 'Captain', device_name: 'Bee 1' })
    await flush()
    expect(getOpenSOS).toHaveBeenCalled()
    expect(sos.sosAlerts).toHaveLength(1)
    expect(sos.sosAlerts[0]).toMatchObject({ id: 'a1', full_name: 'Ivan Petrov' })
  })

  it('the refetch completes the alert without losing its id [T546]', async () => {
    getOpenSOS.mockResolvedValue([{ id: 'a1', device_id: 'd1', full_name: 'Ivan Petrov', notes: 'n', dev_sn: 1001 }])
    const { sos } = seeded()
    sos.applySOSAlert(thinAlert())
    await flush()
    expect(sos.sosAlerts).toHaveLength(1)
    expect(sos.sosAlerts[0]).toMatchObject({ id: 'a1', device_id: 'd1', notes: 'n' })
  })

  it('two alerts in a burst cause one refetch at a time [T546]', async () => {
    const d = deferred()
    getOpenSOS.mockReturnValueOnce(d.promise).mockResolvedValue([])
    const { sos } = seeded()
    sos.applySOSAlert(thinAlert())
    sos.applySOSAlert(thinAlert({ id: 'a2', device_id: 'd2' }))
    sos.applySOSAlert(thinAlert({ id: 'a3', device_id: 'd3' }))
    expect(getOpenSOS).toHaveBeenCalledTimes(1)
    d.resolve([])
    await flush()
    expect(getOpenSOS).toHaveBeenCalledTimes(2)
  })

  it('B1: an alert pushed while a direct fetchSOS is in flight survives it [T546]', async () => {
    const a = deferred(), b = deferred()
    getOpenSOS.mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise)
    const { sos } = seeded()
    const tick = sos.fetchSOS()                  // F_a, as the tick does
    sos.applySOSAlert(thinAlert())               // push; requestSOS starts F_b
    await flush()
    b.resolve([{ id: 'a1', device_id: 'd1', full_name: 'Ivan Petrov' }])   // F_b answers
    await flush()
    a.resolve([])                                // F_a answers without the alert
    await tick
    await flush()
    expect(sos.sosAlerts.map(x => x.device_id)).toEqual(['d1'])
  })

  it('B1: a direct fetchSOS racing a second direct fetchSOS keeps a pushed alert [T546]', async () => {
    const a = deferred(), b = deferred()
    getOpenSOS.mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise).mockResolvedValue([{ id: 'a1', device_id: 'd1' }])
    const { sos } = seeded()
    const f1 = sos.fetchSOS()
    const f2 = sos.fetchSOS()
    sos.applySOSAlert(thinAlert())
    await flush()
    b.resolve([])
    a.resolve([])
    await Promise.allSettled([f1, f2])
    await flush()
    expect(sos.sosAlerts.map(x => x.device_id)).toContain('d1')
  })

  it('a null full_name in a message does not blank the name of the toast or the alert [T546]', async () => {
    getOpenSOS.mockResolvedValue([])
    const { tracking, sos } = seeded()
    tracking.positions.d1.sos_active = false
    tracking.applyLocationUpdate({ type: 'location_update', device_id: 'd1', user_id: 'u1', full_name: null, sos_active: true, latitude: 42, longitude: 23 })
    expect(sos.sosNotifications[0].name).toBe('Ivan Petrov')
    sos.applySOSAlert(thinAlert({ full_name: 'Ivan Petrov' }))
    sos.applySOSAlert(thinAlert({ full_name: null }))
    expect(sos.sosAlerts[0].full_name).toBe('Ivan Petrov')
  })
})
