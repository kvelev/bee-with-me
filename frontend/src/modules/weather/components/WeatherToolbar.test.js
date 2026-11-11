import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'

import WeatherToolbar from './WeatherToolbar.vue'
import { useWeatherUi } from '../ui.js'
import { WEATHER_LAYERS } from '../layers.js'
import { i18n } from '../../../i18n/index.js'

const mountBar = (basemap) => {
  const context = { activeBasemap: ref(basemap) }
  const wrapper = mount(WeatherToolbar, { props: { context }, global: { plugins: [i18n] } })
  return { wrapper, context }
}

describe('WeatherToolbar', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('the buttons show only on the satellite and offline basemaps [T522]', async () => {
    expect(WEATHER_LAYERS.map((l) => l.id)).toEqual(['clouds_new', 'precipitation_new', 'wind_new', 'temp_new'])
    const { wrapper, context } = mountBar('osm')
    expect(wrapper.findAll('button.bm-btn-weather')).toHaveLength(0)
    context.activeBasemap.value = 'satellite'
    await wrapper.vm.$nextTick()
    expect(wrapper.findAll('button.bm-btn.bm-btn-weather')).toHaveLength(4)
    expect(wrapper.find('.bm-row-break').exists()).toBe(true)
    context.activeBasemap.value = 'offline'
    await wrapper.vm.$nextTick()
    expect(wrapper.findAll('button.bm-btn-weather')).toHaveLength(4)
    context.activeBasemap.value = 'topo'
    await wrapper.vm.$nextTick()
    expect(wrapper.findAll('button.bm-btn-weather')).toHaveLength(0)
  })

  it('a click switches the layer on and a second click switches it off [T522]', async () => {
    const { wrapper } = mountBar('satellite')
    const ui = useWeatherUi()
    const buttons = wrapper.findAll('button.bm-btn-weather')
    await buttons[2].trigger('click')
    expect(ui.layerId).toBe('wind_new')
    expect(wrapper.findAll('button.bm-btn-weather')[2].classes()).toContain('active')
    await buttons[1].trigger('click')
    expect(ui.layerId).toBe('precipitation_new')
    await wrapper.findAll('button.bm-btn-weather')[1].trigger('click')
    expect(ui.layerId).toBe(null)
    expect(wrapper.findAll('button.bm-btn-weather.active')).toHaveLength(0)
  })
})
