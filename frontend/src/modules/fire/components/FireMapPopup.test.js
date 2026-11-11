import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'

vi.mock('../../../api', () => ({
  getFireHotspots: vi.fn(), getFireBurntAreas: vi.fn(), getFireStatus: vi.fn(),
  getFireAlerts: vi.fn(), getSuppressionZones: vi.fn(),
  dismissFireHotspot: vi.fn(), extinguishFieldReport: vi.fn(),
}))

import FireMapPopup from './FireMapPopup.vue'
import FirePopup from './FirePopup.vue'
import { useFireStore } from '../store.js'
import { useFireUi } from '../ui.js'
import { ApiError } from '../../../api/client'
import { i18n } from '../../../i18n/index.js'
import en from '../../../i18n/en.js'

const NOW = new Date().toISOString()
const props = (over = {}) => ({ id: 'h1', source: 'viirs', state: 'active', acquired_at: NOW, ...over })
const feature = (over = {}) => ({
  type: 'Feature', id: 'h1', geometry: { type: 'Point', coordinates: [24.5, 42.5] }, properties: props(over),
})

function setup({ admin = true, selection } = {}) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useFireStore()
  store.hotspots = { type: 'FeatureCollection', features: [feature()] }
  // The overlay coordinate is "projected": the fake projection shifts it so a missing conversion shows.
  const context = { isAdmin: ref(admin), mapKit: { toLonLat: vi.fn((c) => [c[0] - 100, c[1] - 100]) } }
  const sel = selection ?? { kind: 'hotspot', properties: props(), coordinate: [124.5, 142.5] }
  const w = mount(FireMapPopup, { props: { selection: sel, context }, global: { plugins: [pinia, i18n] } })
  return { w, store, context, sel }
}

describe('FireMapPopup', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.global.locale.value = 'en'
  })
  afterEach(() => { document.body.innerHTML = '' })

  it('passes kind, properties, lon-lat, admin flag, busy and error text to the popup [T508]', () => {
    const { w, context, sel } = setup()
    const p = w.findComponent(FirePopup).props()
    expect(p.kind).toBe('hotspot')
    expect(p.properties).toEqual(sel.properties)
    expect(p.lonLat).toEqual([24.5, 42.5])
    expect(context.mapKit.toLonLat).toHaveBeenCalledWith([124.5, 142.5])
    expect(p.isAdmin).toBe(true)
    expect(p.busy).toBe(false)
    expect(p.errorText).toBe('')
  })

  it('a viewer gets the admin flag off and a selection without coordinate gets no lon-lat [T508]', () => {
    const { w } = setup({ admin: false, selection: { kind: 'burnt_area', properties: { id: 'b1' } } })
    const p = w.findComponent(FirePopup).props()
    expect(p.isAdmin).toBe(false)
    expect(p.lonLat).toBeNull()
  })

  it('dismiss calls the store, shows the server copy on success and the error text on failure [T508]', async () => {
    const { w, store } = setup()
    store.dismissHotspot = vi.fn(async (id, notes) => {
      store.hotspots = { type: 'FeatureCollection', features: [feature({ state: 'dismissed', dismiss_notes: notes })] }
    })
    await w.findComponent(FirePopup).vm.$emit('dismiss', { id: 'h1', notes: 'solar' })
    await flushPromises()
    expect(store.dismissHotspot).toHaveBeenCalledWith('h1', 'solar')
    expect(w.findComponent(FirePopup).props('properties')).toMatchObject({ state: 'dismissed', dismiss_notes: 'solar' })
    expect(w.emitted('close')).toBeUndefined()   // the popup stays open and shows the changed row

    store.dismissHotspot = vi.fn(async () => { throw new ApiError('Hotspot not found', 404) })
    await w.findComponent(FirePopup).vm.$emit('dismiss', { id: 'h1', notes: '' })
    await flushPromises()
    expect(w.findComponent(FirePopup).props('errorText')).toBe(en.fire.errors.notFound)
    expect(w.findComponent(FirePopup).props('busy')).toBe(false)
  })

  it('a second action while one runs is ignored [T508]', async () => {
    const { w, store } = setup()
    let release
    store.extinguish = vi.fn(() => new Promise((resolve) => { release = resolve }))
    const popup = w.findComponent(FirePopup)
    popup.vm.$emit('extinguish', { id: 'h1' })
    await flushPromises()
    expect(popup.props('busy')).toBe(true)
    popup.vm.$emit('extinguish', { id: 'h1' })
    popup.vm.$emit('dismiss', { id: 'h1', notes: '' })
    await flushPromises()
    expect(store.extinguish).toHaveBeenCalledTimes(1)
    release()
    await flushPromises()
    expect(popup.props('busy')).toBe(false)
  })

  it('a new selection forgets the earlier server copy and error [T508]', async () => {
    const { w, store, context } = setup()
    store.extinguish = vi.fn(async () => { throw new ApiError('Hotspot not found', 404) })
    await w.findComponent(FirePopup).vm.$emit('extinguish', { id: 'h1' })
    await flushPromises()
    expect(w.findComponent(FirePopup).props('errorText')).not.toBe('')
    const next = { kind: 'hotspot', properties: props({ id: 'h2' }), coordinate: [1, 2] }
    await w.setProps({ selection: next, context })
    expect(w.findComponent(FirePopup).props('errorText')).toBe('')
    expect(w.findComponent(FirePopup).props('properties')).toEqual(next.properties)
  })

  it('create zone opens the zone dialog at the popup position [T508]', async () => {
    const { w } = setup()
    const ui = useFireUi()
    await w.findComponent(FirePopup).vm.$emit('create-zone')
    expect(ui.dialog).toEqual({ kind: 'zone', target: { latitude: 42.5, longitude: 24.5 } })
    expect(w.emitted('close')).toHaveLength(1)
  })

  it('switching the layer off closes the popup of that layer only [T508]', async () => {
    const { w, store } = setup()
    store.layers = { burnt: true, hotspots: true, zones: false }
    await flushPromises()
    store.layers = { burnt: false, hotspots: true, zones: false }
    await flushPromises()
    expect(w.emitted('close')).toBeUndefined()
    store.layers = { burnt: false, hotspots: false, zones: false }
    await flushPromises()
    expect(w.emitted('close')).toHaveLength(1)
  })
})
