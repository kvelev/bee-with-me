import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import { ref, shallowRef } from 'vue'

vi.mock('../../../api', () => ({
  getFireHotspots: vi.fn(), getFireBurntAreas: vi.fn(), getFireStatus: vi.fn(),
  getFireAlerts: vi.fn(), getSuppressionZones: vi.fn(),
}))

import * as api from '../../../api'
import FireMapPanel from './FireMapPanel.vue'
import fireManifest from '../index.js'
import { FIRE_MAP_LAYERS } from '../map/layers.js'
import { useFireStore } from '../store.js'
import { i18n } from '../../../i18n/index.js'
import en from '../../../i18n/en.js'

const EMPTY = { type: 'FeatureCollection', features: [], meta: {} }

class FakeOverlay {
  constructor(opts) { this.element = opts.element; this.position = undefined }
  setPosition(p) { this.position = p }
}

function fakeMap() {
  const view = { animate: vi.fn() }
  return {
    overlays: [],
    addOverlay(o) { this.overlays.push(o) },
    removeOverlay(o) { this.overlays = this.overlays.filter((x) => x !== o) },
    updateSize: vi.fn(),
    getView: () => view,
    view,
  }
}

function makeContext({ admin = true, withMap = true, active = true } = {}) {
  const map = withMap ? fakeMap() : null
  const facade = {
    setHotspots: vi.fn(() => true),
    setBurntAreas: vi.fn(() => true),
    setZones: vi.fn(),
    setFireLayerVisible: vi.fn(),
    setFireLabels: vi.fn(),
  }
  const context = {
    hostMap: shallowRef(map),
    facade,
    mapKit: { Overlay: FakeOverlay, fromLonLat: (c) => c },
    isAdmin: ref(admin),
    mapActive: ref(active),
  }
  return { context, facade, map }
}

const mountPanel = (context) => mount(FireMapPanel, {
  props: { context }, attachTo: document.body, global: { plugins: [i18n] },
})

describe('FireMapPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    document.body.innerHTML = ''
    setActivePinia(createPinia())
    api.getFireHotspots.mockResolvedValue(EMPTY)
    api.getFireBurntAreas.mockResolvedValue(EMPTY)
    api.getSuppressionZones.mockResolvedValue([])
  })
  afterEach(() => { vi.useRealTimers() })

  it('layers remembered from the last session are shown on mount, zones only for an admin [T507]', async () => {
    const fire = useFireStore()
    fire.layers = { burnt: true, hotspots: false, zones: true }
    const admin = makeContext({ admin: true })
    const wa = mountPanel(admin.context)
    await flushPromises()
    expect(admin.facade.setFireLayerVisible).toHaveBeenCalledWith('burnt', true)
    expect(admin.facade.setFireLayerVisible).toHaveBeenCalledWith('hotspots', false)
    expect(admin.facade.setFireLayerVisible).toHaveBeenCalledWith('zones', true)
    wa.unmount()

    const viewer = makeContext({ admin: false })
    const wv = mountPanel(viewer.context)
    await flushPromises()
    expect(viewer.facade.setFireLayerVisible).toHaveBeenCalledWith('zones', false)
    wv.unmount()
  })

  it('a change of a layer flag reaches the map in the same tick [T507]', async () => {
    const { context, facade } = makeContext()
    const w = mountPanel(context)
    await flushPromises()
    facade.setFireLayerVisible.mockClear()
    useFireStore().layers.hotspots = true            // no await: the watcher is synchronous
    expect(facade.setFireLayerVisible.mock.calls).toEqual([['hotspots', true]])
    w.unmount()
  })

  it('a feed the map cannot read is marked failed [T507]', async () => {
    const { context, facade } = makeContext()
    facade.setHotspots.mockReturnValue(false)
    const fire = useFireStore()
    const spy = vi.spyOn(fire, 'markFeedFailed')
    const w = mountPanel(context)
    await flushPromises()
    expect(spy).toHaveBeenCalledWith('hotspots')
    w.unmount()
  })

  it('the pill shows the feed time and the attribution line only while a data layer is on [T507]', async () => {
    const { context } = makeContext()
    const fire = useFireStore()
    fire.layers = { burnt: false, hotspots: false, zones: true }
    const w = mountPanel(context)
    await flushPromises()
    expect(w.find('.fire-pill').exists()).toBe(false)
    expect(w.find('.fire-attribution').exists()).toBe(false)

    fire.layers = { burnt: false, hotspots: true, zones: false }
    await flushPromises()
    fire.fetchedAt = '2026-11-11T10:05:00Z'
    await flushPromises()
    expect(w.find('.fire-pill').exists()).toBe(true)
    expect(w.find('.fire-attribution').text()).toBe(en.fire.attribution)
    const time = new Date('2026-11-11T10:05:00Z').toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    expect(w.find('.fire-pill .fire-time').text()).toBe(time)
    w.unmount()
  })

  it('a focus request centres the map and shows the ring for 8 s, and unmount removes the overlay [T507]', async () => {
    const { context, map } = makeContext()
    const w = mountPanel(context)
    await flushPromises()
    expect(map.overlays).toHaveLength(1)
    vi.useFakeTimers()
    const fire = useFireStore()
    fire.requestFocus(42.7, 24.17)
    await flushPromises()
    expect(fire.focusRequest).toBeNull()
    expect(fire.layers.hotspots).toBe(true)
    expect(map.view.animate).toHaveBeenCalledWith(expect.objectContaining({ center: [24.17, 42.7], zoom: 12 }))
    expect(map.overlays[0].position).toEqual([24.17, 42.7])
    expect(w.find('[data-testid="fire-focus-ring"]').exists()).toBe(true)

    await vi.advanceTimersByTimeAsync(7_900)
    expect(w.find('[data-testid="fire-focus-ring"]').exists()).toBe(true)
    await vi.advanceTimersByTimeAsync(200)
    expect(w.find('[data-testid="fire-focus-ring"]').exists()).toBe(false)
    expect(map.overlays[0].position).toBeUndefined()

    w.unmount()
    expect(map.overlays).toHaveLength(0)
  })

  it('a focus request waits while the map is not on screen [T507]', async () => {
    const { context, map } = makeContext({ active: false })
    const w = mountPanel(context)
    await flushPromises()
    const fire = useFireStore()
    fire.requestFocus(42.7, 24.17)
    await flushPromises()
    expect(fire.focusRequest).not.toBeNull()
    expect(map.view.animate).not.toHaveBeenCalled()
    context.mapActive.value = true
    await flushPromises()
    expect(fire.focusRequest).toBeNull()
    expect(map.view.animate).toHaveBeenCalled()
    w.unmount()
  })

  it('the toggle pair of the manifest flips the store flag [T507]', async () => {
    expect(fireManifest.mapLayers).toBe(FIRE_MAP_LAYERS)
    const fire = useFireStore()
    for (const key of ['burnt', 'hotspots', 'zones']) {
      const toggle = FIRE_MAP_LAYERS.find((l) => l.id === `fire-${key}`).toggle
      expect(toggle.key).toBe(key)
      expect(toggle.isOn()).toBe(false)
      toggle.set(true)
      expect(fire.layers[key]).toBe(true)
      expect(toggle.isOn()).toBe(true)
      toggle.set(false)
      expect(toggle.isOn()).toBe(false)
    }
    await flushPromises()
  })
})
