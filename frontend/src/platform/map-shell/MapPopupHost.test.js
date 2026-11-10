import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { mount } from '@vue/test-utils'

const created = vi.hoisted(() => [])
vi.mock('ol/Overlay', () => ({
  default: class {
    constructor(options) {
      this.options = options
      this.positions = []
      this.setPosition = vi.fn((p) => { this.positions.push(p) })
      created.push(this)
    }
  },
}))

import MapPopupHost from './MapPopupHost.vue'

const fakeMap = () => ({ addOverlay: vi.fn(), removeOverlay: vi.fn() })
const A = { id: 'a', kinds: ['hotspot'], component: {} }
const B = { id: 'b', kinds: ['burnt_area'], component: {} }

const slotFn = ({ popup, selection }) => h('p', { 'data-testid': 'content', 'data-popup': popup.id }, selection.kind)

function mountHost(props = {}, slots = { default: slotFn }) {
  return mount(MapPopupHost, {
    props: { map: fakeMap(), popups: [A, B], selection: null, anchorClass: 'my-anchor', ...props },
    slots,
  })
}

let errSpy
beforeEach(() => {
  created.length = 0
  errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
})
afterEach(() => { errSpy.mockRestore() })

describe('MapPopupHost', () => {
  it('adds one overlay on mount and removes it on unmount [T424]', () => {
    const map = fakeMap()
    const w = mountHost({ map })
    expect(created).toHaveLength(1)
    expect(map.addOverlay).toHaveBeenCalledTimes(1)
    expect(map.addOverlay).toHaveBeenCalledWith(created[0])
    expect(created[0].options).toMatchObject({ positioning: 'bottom-center', offset: [0, -16], stopEvent: true })
    expect(created[0].options.autoPan.margin).toBe(24)
    expect(w.element.classList.contains('my-anchor')).toBe(true)
    w.unmount()
    expect(map.removeOverlay).toHaveBeenCalledTimes(1)
    expect(map.removeOverlay).toHaveBeenCalledWith(created[0])
  })

  it('a map prop that goes from null to a map after mount gets the overlay then [T424]', async () => {
    const map = fakeMap()
    const w = mountHost({ map: null })
    expect(created).toHaveLength(0)
    await w.setProps({ map })
    expect(map.addOverlay).toHaveBeenCalledTimes(1)
    await w.setProps({ map: null })
    expect(map.removeOverlay).toHaveBeenCalledTimes(1)
  })

  it('renders the slot with the popup that claims the selection kind [T424]', async () => {
    const w = mountHost({ selection: { kind: 'burnt_area', coordinate: [1, 2] } })
    await nextTick()
    const c = w.get('[data-testid="content"]')
    expect(c.attributes('data-popup')).toBe('b')
    expect(c.text()).toBe('burnt_area')
  })

  it('uses a shorter autoPan animation when reduced motion is asked for [T424]', () => {
    const original = window.matchMedia
    window.matchMedia = () => ({ matches: true })
    mountHost()
    window.matchMedia = original
    expect(created[0].options.autoPan.animation.duration).toBe(0)
  })

  it('positions the overlay after the content is rendered and clears it when the selection goes [T424]', async () => {
    const w = mountHost()
    await w.setProps({ selection: { kind: 'hotspot', coordinate: [3, 4] } })
    await nextTick()
    expect(created[0].setPosition).toHaveBeenLastCalledWith([3, 4])
    expect(w.find('[data-testid="content"]').exists()).toBe(true)
    await w.setProps({ selection: null })
    await nextTick()
    expect(created[0].setPosition).toHaveBeenLastCalledWith(undefined)
    expect(w.find('[data-testid="content"]').exists()).toBe(false)
  })

  it('an unknown kind renders nothing and clears the position [T424]', async () => {
    const w = mountHost()
    await w.setProps({ selection: { kind: 'hotspot', coordinate: [3, 4] } })
    await nextTick()
    await w.setProps({ selection: { kind: 'mystery', coordinate: [5, 6] } })
    await nextTick()
    expect(w.find('[data-testid="content"]').exists()).toBe(false)
    expect(created[0].setPosition).toHaveBeenLastCalledWith(undefined)
  })

  it('a null map renders the anchor and touches no overlay [T424]', async () => {
    const w = mountHost({ map: null, selection: { kind: 'hotspot', coordinate: [1, 1] } })
    await nextTick()
    expect(w.element.classList.contains('my-anchor')).toBe(true)
    expect(created).toHaveLength(0)
    w.unmount()
    expect(created).toHaveLength(0)
  })

  describe('error isolation', () => {
    const Boom = defineComponent({ props: { kind: String }, setup(p) { return () => { if (p.kind === 'hotspot') throw new Error('boom'); return h('i', { 'data-testid': 'ok' }, 'fine') } } })
    const boomSlot = ({ selection }) => h(Boom, { kind: selection.kind })

    it('a slot child that throws while rendering does not break the host, is logged by popup id, and a later selection renders again [T424]', async () => {
      const w = mountHost({}, { default: boomSlot })
      await w.setProps({ selection: { kind: 'hotspot', coordinate: [1, 1] } })
      await nextTick()
      expect(w.element.classList.contains('my-anchor')).toBe(true)
      expect(w.find('[data-testid="ok"]').exists()).toBe(false)
      const logged = errSpy.mock.calls.find((c) => c[0] === '[map-shell] popup "%s" failed')
      expect(logged).toBeTruthy()
      expect(logged[1]).toBe('a')
      expect(created[0].setPosition).toHaveBeenLastCalledWith(undefined)

      await w.setProps({ selection: { kind: 'burnt_area', coordinate: [2, 2] } })
      await nextTick()
      expect(w.find('[data-testid="ok"]').exists()).toBe(true)
      expect(created[0].setPosition).toHaveBeenLastCalledWith([2, 2])
    })

    it('an overlay position call that throws is logged by popup id and renders nothing [T424]', async () => {
      const w = mountHost()
      await nextTick()
      created[0].setPosition = vi.fn(() => { throw new Error('ol broke') })
      await w.setProps({ selection: { kind: 'hotspot', coordinate: [1, 1] } })
      await nextTick()
      await nextTick()
      const logged = errSpy.mock.calls.find((c) => c[0] === '[map-shell] popup "%s" failed')
      expect(logged).toBeTruthy()
      expect(logged[1]).toBe('a')
      expect(w.find('[data-testid="content"]').exists()).toBe(false)
      created[0].setPosition = vi.fn()
      await w.setProps({ selection: { kind: 'burnt_area', coordinate: [2, 2] } })
      await nextTick()
      expect(w.find('[data-testid="content"]').exists()).toBe(true)
      expect(created[0].setPosition).toHaveBeenLastCalledWith([2, 2])
    })
  })

  describe('popup list problems', () => {
    const problemLogs = () => errSpy.mock.calls.filter((c) => c.join(' ').includes('popups'))

    it('two popups with different ids claiming the same kind log a problem naming the kind and both ids [T424]', () => {
      mountHost({ popups: [A, { id: 'c', kinds: ['hotspot'], component: {} }] })
      const text = problemLogs().map((c) => c.join(' ')).join('\n')
      expect(text).toContain('hotspot')
      expect(text).toContain('"a"')
      expect(text).toContain('"c"')
    })

    it('the same kind listed twice by one popup is not a problem [T424]', () => {
      mountHost({ popups: [{ id: 'a', kinds: ['hotspot', 'hotspot'], component: {} }] })
      expect(problemLogs()).toHaveLength(0)
    })

    it('unique kinds log nothing [T424]', () => {
      mountHost()
      expect(errSpy).not.toHaveBeenCalled()
    })
  })
})
