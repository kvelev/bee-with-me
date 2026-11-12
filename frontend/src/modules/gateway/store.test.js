import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../../api', () => ({ getSerialStatus: vi.fn() }))

import { getSerialStatus } from '../../api'
import { useGatewayStore } from './store.js'

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

describe('gateway store', () => {
  it('applyStatus replaces the status [T630]', () => {
    const store = useGatewayStore()
    expect(store.status).toBeNull()
    store.applyStatus({ type: 'serial_status', connected: true, port: 'COM3', frames_received: 4 })
    expect(store.status).toEqual({ connected: true, port: 'COM3', frames_received: 4 })
    store.applyStatus({ type: 'serial_status', connected: false, port: 'COM3', frames_received: 4 })
    expect(store.status.connected).toBe(false)
  })

  it('fetchStatus stores the answer [T630]', async () => {
    getSerialStatus.mockResolvedValue({ connected: true, port: '/dev/ttyACM0', frames_received: 9 })
    const store = useGatewayStore()
    await store.fetchStatus()
    expect(store.status).toEqual({ connected: true, port: '/dev/ttyACM0', frames_received: 9 })
  })

  it('a failed fetchStatus leaves the status and does not reject [T630]', async () => {
    const store = useGatewayStore()
    store.applyStatus({ connected: true, port: 'COM3', frames_received: 1 })
    getSerialStatus.mockRejectedValue(new Error('port not configured'))
    await expect(store.fetchStatus()).resolves.toBeUndefined()
    expect(store.status.port).toBe('COM3')
    getSerialStatus.mockRejectedValue(Object.assign(new Error('Unauthorized'), { response: { status: 401 } }))
    await expect(store.fetchStatus()).resolves.toBeUndefined()
    expect(store.status.port).toBe('COM3')
  })

  it('a null answer leaves the status unchanged and does not reject [T630]', async () => {
    const store = useGatewayStore()
    getSerialStatus.mockResolvedValue(null)
    await expect(store.fetchStatus()).resolves.toBeUndefined()
    expect(store.status).toBeNull()
    store.applyStatus({ connected: false, port: 'COM3' })
    await store.fetchStatus()
    expect(store.status).toEqual({ connected: false, port: 'COM3' })
  })
})
