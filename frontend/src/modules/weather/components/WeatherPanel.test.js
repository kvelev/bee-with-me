import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import { ref, shallowRef, nextTick } from 'vue'

vi.mock('../../../api', () => ({ getWeatherCurrent: vi.fn(), getWeatherBox: vi.fn() }))

import * as api from '../../../api'
import WeatherPanel from './WeatherPanel.vue'
import { useWeatherUi } from '../ui.js'
import { i18n } from '../../../i18n/index.js'

const OWM = {
  main: { temp: 12.3, feels_like: 11, humidity: 55 }, wind: { speed: 4, deg: 90 },
  clouds: { all: 20 }, weather: [{ description: 'clear sky', icon: '01d' }], name: 'Sofia',
}
const OPEN_METEO = [{ latitude: 42.5, longitude: 23.5, current: { wind_speed_10m: 3, wind_direction_10m: 200, wind_gusts_10m: 5 } }]

function fakeMap() {
  const view = {
    getCenter: () => [23, 42], calculateExtent: () => [22, 41, 24, 43], getZoom: () => 7,
    on: vi.fn(() => ({ viewKey: true })), un: vi.fn(),
  }
  return {
    on: vi.fn(), un: vi.fn(), getSize: () => [800, 600], getView: () => view, view,
    getPixelFromCoordinate: () => [10, 10], getCoordinateFromPixel: () => [23, 42],
  }
}

function makeContext(map = fakeMap()) {
  const unByKey = vi.fn()
  return {
    map,
    unByKey,
    context: {
      hostMap: shallowRef(map),
      facade: { setWeatherLayer: vi.fn() },
      mapKit: { toLonLat: (c) => c, unByKey },
      activeBasemap: ref('satellite'),
    },
  }
}

const mountPanel = (context) => mount(WeatherPanel, {
  props: { context }, attachTo: document.body, global: { plugins: [i18n] },
})
const moveend = (map) => map.on.mock.calls.find((c) => c[0] === 'moveend')?.[1]

describe('WeatherPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    document.body.innerHTML = ''
    setActivePinia(createPinia())
    api.getWeatherCurrent.mockResolvedValue(OWM)
    api.getWeatherBox.mockResolvedValue({ list: [] })
    // jsdom lays nothing out: give the map element a size, as a browser would (the canvas is 260 px narrower).
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ width: 1060, height: 600, top: 0, left: 0, right: 1060, bottom: 600 })
    // jsdom has no canvas: a context whose every method is a no-op.
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(() => new Proxy({}, {
      get: (_t, k) => (k === 'canvas' ? document.createElement('canvas') : () => ({ width: 1, addColorStop: () => {} })),
      set: () => true,
    }))
  })
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

  it('switching a layer on hands the tile URL and the recolour function to the map [T522]', async () => {
    const { context } = makeContext()
    mountPanel(context)
    useWeatherUi().toggle('clouds_new')
    await flushPromises()
    expect(context.facade.setWeatherLayer).toHaveBeenCalledTimes(1)
    const [url, recolor] = context.facade.setWeatherLayer.mock.calls[0]
    expect(url).toBe('/api/weather/tiles/clouds_new/{z}/{x}/{y}.png')
    expect(typeof recolor).toBe('function')
    expect(api.getWeatherCurrent).toHaveBeenCalledWith(42, 23)
    expect(document.querySelector('.weather-panel')).not.toBeNull()
    expect(document.querySelector('.weather-legend .legend-bar')).not.toBeNull()
  })

  it('switching it off clears the layer and the info panel [T522]', async () => {
    const { context } = makeContext()
    mountPanel(context)
    const ui = useWeatherUi()
    ui.toggle('clouds_new')
    await flushPromises()
    ui.toggle('clouds_new')
    await flushPromises()
    expect(context.facade.setWeatherLayer).toHaveBeenLastCalledWith(null, null)
    expect(document.querySelector('.weather-panel')).toBeNull()
  })

  it('the panel attaches to a map that appears after mount [T522]', async () => {
    const map = fakeMap()
    const { context } = makeContext(map)
    context.hostMap.value = null
    mountPanel(context)
    expect(map.on).not.toHaveBeenCalled()
    context.hostMap.value = map
    await nextTick()
    expect(map.on).toHaveBeenCalledWith('moveend', expect.any(Function))
  })

  it('a move of the map fetches the weather once after the debounce [T522]', async () => {
    vi.useFakeTimers()
    const { context, map } = makeContext()
    mountPanel(context)
    useWeatherUi().toggle('clouds_new')
    await vi.advanceTimersByTimeAsync(0)
    api.getWeatherCurrent.mockClear()
    const handler = moveend(map)
    handler(); handler()
    await vi.advanceTimersByTimeAsync(699)
    expect(api.getWeatherCurrent).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(2)
    expect(api.getWeatherCurrent).toHaveBeenCalledTimes(1)
  })

  it('a denied box request falls back and is not repeated [T522]', async () => {
    vi.useFakeTimers()
    api.getWeatherBox.mockResolvedValue({ denied: true })
    const fetchMock = vi.fn(async () => ({ ok: true, json: async () => OPEN_METEO }))
    vi.stubGlobal('fetch', fetchMock)
    const { context, map } = makeContext()
    mountPanel(context)
    useWeatherUi().toggle('wind_new')
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(0)
    expect(api.getWeatherBox).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(document.body.textContent).toContain('Open-Meteo.com')
    moveend(map)()
    await vi.advanceTimersByTimeAsync(800)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(api.getWeatherBox).toHaveBeenCalledTimes(1)
  })

  it('unmount stops the animation and removes the map listener [T522]', async () => {
    vi.useFakeTimers()
    const raf = vi.spyOn(globalThis, 'requestAnimationFrame').mockImplementation(() => 7)
    const caf = vi.spyOn(globalThis, 'cancelAnimationFrame').mockImplementation(() => {})
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, json: async () => [] })))
    const { context, map, unByKey } = makeContext()
    const wrapper = mountPanel(context)
    useWeatherUi().toggle('wind_new')
    await vi.advanceTimersByTimeAsync(0)
    expect(raf).toHaveBeenCalled()
    const handler = moveend(map)
    handler()                           // a pending debounce at unmount time
    wrapper.unmount()
    expect(caf).toHaveBeenCalledWith(7)
    expect(map.un).toHaveBeenCalledWith('moveend', handler)
    expect(unByKey).toHaveBeenCalled()  // the view listener of the animation
    expect(vi.getTimerCount()).toBe(0)
  })
})
