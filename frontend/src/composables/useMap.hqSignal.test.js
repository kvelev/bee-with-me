import { describe, it, expect, vi, afterEach } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { useMap } from './useMap'

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} }

afterEach(() => {
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})

function setup() {
  const el = document.createElement('div')
  document.body.append(el)
  let api
  const w = mount(defineComponent({
    setup() {
      api = useMap(ref(el), ref([]), ref({}), vi.fn(), vi.fn(), ref({}), vi.fn())
      return () => h('div')
    },
  }))
  return { api, w }
}

describe('setHQPlacementMode result', () => {
  it('returns true with the real settings entry [T580]', () => {
    const { api, w } = setup()
    expect(api.setHQPlacementMode(true)).toBe(true)
    expect(api.setHQPlacementMode(false)).toBe(true)
    w.unmount()
  })

  it('returns false when the settings entry is missing and the console line stays [T580]', async () => {
    vi.resetModules()
    vi.doMock('../modules/mapEntries', async () => {
      const real = await vi.importActual('../modules/settings/map/index.js')
      return { MAP_MODULES: [{ ...real.default, setup() { throw new Error('boom') } }] }
    })
    const { useMap: useMapBroken } = await import('./useMap')
    const error = vi.spyOn(console, 'error').mockImplementation(() => {})
    const el = document.createElement('div')
    document.body.append(el)
    let api
    const w = mount(defineComponent({
      setup() {
        api = useMapBroken(ref(el), ref([]), ref({}), vi.fn(), vi.fn(), ref({}), vi.fn())
        return () => h('div')
      },
    }))
    error.mockClear()
    expect(api.setHQPlacementMode(true)).toBe(false)
    expect(error).toHaveBeenCalledTimes(1)
    w.unmount()
    vi.doUnmock('../modules/mapEntries')
  })
})
