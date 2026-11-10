import { describe, it, expect, vi, afterEach } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { mount } from '@vue/test-utils'

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} }

// The settings map entry fails to install (its setup throws): the shell returns an empty api.
vi.mock('../modules/mapEntries', async () => {
  const real = await vi.importActual('../modules/settings/map/index.js')
  return { MAP_MODULES: [{ ...real.default, setup() { throw new Error('boom') } }] }
})

import { useMap } from './useMap'

afterEach(() => {
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})

describe('HQ when the settings map entry failed to install', () => {
  it('setHQ and setHQPlacementMode are no-ops that log once and the rest of the map works [T427]', () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {})
    const el = document.createElement('div')
    document.body.append(el)
    let api
    const w = mount(defineComponent({
      setup() {
        api = useMap(ref(el), ref([]), ref({}), vi.fn(), vi.fn(), ref({}), vi.fn())
        return () => h('div')
      },
    }))
    error.mockClear()

    expect(() => { api.setHQ({ lat: 42.5, lon: 25 }); api.setHQ(null); api.setHQPlacementMode(true) }).not.toThrow()
    expect(error).toHaveBeenCalledTimes(1)
    expect(() => api.setRepeaterPlacementMode(true)).not.toThrow()
    expect(api.map()).toBeTruthy()
    w.unmount()
  })
})
