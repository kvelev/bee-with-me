import { describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import * as freshnessOld from '../../lib/freshness.js'
import * as photoOld from '../../lib/photoMarker.js'
import * as tooltipOld from '../../lib/trackerTooltip.js'
import { useLocationsStore } from '../../stores/locations.js'
import { checkModules } from '../../platform/registry.js'
import { MODULES } from '../index.js'
import sos, { useSosStore } from '../sos/index.js'
import * as freshness from './lib/freshness.js'
import * as photo from './lib/photoMarker.js'
import * as tooltip from './lib/trackerTooltip.js'
import tracking, { useTrackingStore } from './index.js'

describe('tracking module manifest', () => {
  it('the two manifests are valid and in the module list [T544]', () => {
    expect(MODULES).toContain(tracking)
    expect(MODULES).toContain(sos)
    expect(tracking.name).toBe('tracking')
    expect(tracking.depends).toEqual([])
    expect(checkModules(MODULES)).toEqual([])
    expect(Object.keys(tracking.liveHandlers).sort()).toEqual(['location_update'])
    expect(Object.keys(sos.liveHandlers)).toEqual(['sos_alert'])
  })

  it('the facade and the two stores share state [T544]', () => {
    localStorage.clear()
    setActivePinia(createPinia())
    const facade = useLocationsStore()
    facade.sosAlerts = [{ id: 'a1', device_id: 'd1' }]
    expect(useSosStore().sosAlerts).toEqual([{ id: 'a1', device_id: 'd1' }])
    expect(facade.hasSOS).toBe(true)
    useTrackingStore().positions.d1 = { device_id: 'd1', received_at: new Date().toISOString() }
    expect(facade.positionList.map((p) => p.device_id)).toEqual(['d1'])
    facade.removePosition('d1')
    expect(useSosStore().sosAlerts).toEqual([])
    expect(useTrackingStore().positions.d1).toBeUndefined()
  })

  it('the old library paths are the moved libraries [T544]', () => {
    expect(freshnessOld.freshnessOf).toBe(freshness.freshnessOf)
    expect(photoOld.photoImage).toBe(photo.photoImage)
    expect(tooltipOld.renderTrackerTooltip).toBe(tooltip.renderTrackerTooltip)
  })
})
