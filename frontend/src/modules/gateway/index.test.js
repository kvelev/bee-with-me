import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../../api', async (orig) => ({ ...(await orig()), getSerialStatus: vi.fn() }))

import { getSerialStatus } from '../../api'
import { i18n } from '../../i18n/index.js'
import { collectLiveHandlers, collectLiveHooks } from '../../platform/live/dispatch.js'
import { collectPanels, contributionProblems } from '../../platform/map-shell/contributions.js'
import { checkModules } from '../../platform/registry.js'
import { useLocationsStore } from '../../stores/locations.js'
import { MODULES } from '../index.js'
import tracking from '../tracking/index.js'
import gateway, { useGatewayStore } from './index.js'

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

describe('gateway module manifest', () => {
  it('the gateway manifest is valid and in the module list [T630]', () => {
    expect(MODULES).toContain(gateway)
    expect(gateway).toMatchObject({ name: 'gateway', routes: [], nav: [], mapLayers: [], banners: [], depends: [] })
    expect(checkModules(MODULES)).toEqual([])
    expect(contributionProblems(MODULES)).toEqual([])
    expect(gateway.panels).toHaveLength(1)
    expect(gateway.panels[0]).toMatchObject({ id: 'gateway-status', host: 'map', order: 20 })
    expect(collectPanels(MODULES, 'map').map((p) => p.id)).toContain('gateway-status')
  })

  it('serial_status is handled by gateway and not by tracking [T630]', () => {
    expect(Object.keys(gateway.liveHandlers)).toEqual(['serial_status'])
    expect(Object.keys(tracking.liveHandlers)).toEqual(['location_update'])
    const handlers = collectLiveHandlers(MODULES).get('serial_status')
    expect(handlers).toHaveLength(1)
    handlers[0]({ type: 'serial_status', connected: true, port: 'COM4', frames_received: 2 })
    expect(useGatewayStore().status).toEqual({ connected: true, port: 'COM4', frames_received: 2 })
  })

  it('the status is fetched in setup and on every tick [T630]', async () => {
    getSerialStatus.mockResolvedValue({ connected: true, port: 'COM3', frames_received: 1 })
    const hooks = collectLiveHooks(MODULES)
    expect(hooks.setup).toContain(gateway.live.setup)
    expect(hooks.onTick).toContain(gateway.live.onTick)
    await gateway.live.setup()
    expect(getSerialStatus).toHaveBeenCalledTimes(1)
    await gateway.live.onTick()
    expect(getSerialStatus).toHaveBeenCalledTimes(2)
    await gateway.live.onTick()
    expect(getSerialStatus).toHaveBeenCalledTimes(3)
  })

  it('a status missed at setup arrives with the next tick [T630]', async () => {
    getSerialStatus.mockRejectedValueOnce(new Error('down')).mockResolvedValueOnce({ connected: true, port: 'COM3', frames_received: 5 })
    await gateway.live.setup()
    expect(useGatewayStore().status).toBeNull()
    await gateway.live.onTick()
    expect(useGatewayStore().status).toEqual({ connected: true, port: 'COM3', frames_received: 5 })
  })

  it('the two texts keep their key names [T630]', () => {
    const { te, t } = i18n.global
    for (const locale of ['en', 'bg']) {
      expect(te('map.serialConnected', locale)).toBe(true)
      expect(te('map.serialDisconnected', locale)).toBe(true)
    }
    expect(t('map.serialConnected', {}, { locale: 'en' })).toBe('Gateway connected')
    expect(t('map.serialDisconnected', {}, { locale: 'bg' })).toBe('Gateway изключен')
  })

  it('the facade still returns serialStatus and applySerialStatus [T630]', () => {
    const facade = useLocationsStore()
    expect(facade.serialStatus).toBeNull()
    facade.applySerialStatus({ type: 'serial_status', connected: true, port: 'COM5', frames_received: 7 })
    expect(useGatewayStore().status).toEqual({ connected: true, port: 'COM5', frames_received: 7 })
    expect(facade.serialStatus).toEqual({ connected: true, port: 'COM5', frames_received: 7 })
  })
})
