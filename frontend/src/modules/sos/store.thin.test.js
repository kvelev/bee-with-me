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
})
