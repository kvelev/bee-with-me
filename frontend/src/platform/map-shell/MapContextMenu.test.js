import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'

vi.mock('ol/proj', () => ({ toLonLat: (c) => [c[0] / 100, c[1] / 100] }))

import MapContextMenu from './MapContextMenu.vue'
import { i18n } from '../../i18n/index.js'
import en from '../../i18n/en.js'

const item = (over = {}) => ({
  id: 'one', order: 10, labelKey: 'fire.report.here', testId: 'item-one', onSelect: vi.fn(), ...over,
})
const BOUNDS = { width: 600, height: 420 }

const mounted = []
function mountMenu(items = [item()]) {
  const w = mount(MapContextMenu, { props: { items }, attachTo: document.body, global: { plugins: [i18n] } })
  mounted.push(w)
  return w
}
async function open(w, over = {}) {
  w.vm.open({ coordinate: [2451, 4251], pixel: [200, 150], bounds: BOUNDS, ...over })
  await nextTick()
  await nextTick()
}

let errSpy
beforeEach(() => {
  i18n.global.locale.value = 'en'
  errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
})
afterEach(() => {
  while (mounted.length) mounted.pop().unmount()
  errSpy.mockRestore()
  vi.restoreAllMocks()
  document.body.innerHTML = ''
})

describe('MapContextMenu', () => {
  it('closed by default and with no items it never opens [T425]', async () => {
    const add = vi.spyOn(document, 'addEventListener')
    const w = mountMenu([])
    await open(w)
    expect(w.find('.map-context').exists()).toBe(false)
    expect(add).not.toHaveBeenCalledWith('pointerdown', expect.anything(), true)
    const w2 = mountMenu()
    expect(w2.find('.map-context').exists()).toBe(false)
  })

  it('open shows one menu item per contribution in the given order with its test id and label [T425]', async () => {
    const w = mountMenu([item(), item({ id: 'two', testId: 'item-two', labelKey: 'fire.report.atPosition' })])
    await open(w)
    const menu = w.get('.map-context')
    expect(menu.attributes('role')).toBe('menu')
    const buttons = w.findAll('.mc-item')
    expect(buttons).toHaveLength(2)
    expect(buttons[0].attributes('data-testid')).toBe('item-one')
    expect(buttons[0].attributes('role')).toBe('menuitem')
    expect(buttons[0].attributes('type')).toBe('button')
    expect(buttons[0].text()).toBe(en.fire.report.here)
    expect(buttons[1].attributes('data-testid')).toBe('item-two')
  })

  it('the menu stays inside the bounds [T425]', async () => {
    const w = mountMenu()
    await open(w, { pixel: [500, 400] })
    expect(w.get('.map-context').attributes('style')).toContain('left: 404px')
    expect(w.get('.map-context').attributes('style')).toContain('top: 368px')
    await open(w, { pixel: [1, 1] })
    expect(w.get('.map-context').attributes('style')).toContain('left: 4px')
    expect(w.get('.map-context').attributes('style')).toContain('top: 4px')
    await open(w, { pixel: [500, 400], bounds: { width: 0, height: 0 } })
    expect(w.get('.map-context').attributes('style')).toContain('left: 500px')
    expect(w.get('.map-context').attributes('style')).toContain('top: 400px')
  })

  it('the first item is focused after opening [T425]', async () => {
    const w = mountMenu([item(), item({ id: 'two', testId: 'item-two' })])
    await open(w)
    expect(document.activeElement).toBe(w.findAll('.mc-item')[0].element)
  })

  it('Escape and an outside pointer-down close it and remove the document listeners [T425]', async () => {
    const remove = vi.spyOn(document, 'removeEventListener')
    const w = mountMenu()
    await open(w)
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await nextTick()
    expect(w.find('.map-context').exists()).toBe(false)
    expect(remove).toHaveBeenCalledWith('pointerdown', expect.any(Function), true)
    expect(remove).toHaveBeenCalledWith('keydown', expect.any(Function), true)

    await open(w)
    expect(w.find('.map-context').exists()).toBe(true)
    document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    await nextTick()
    expect(w.find('.map-context').exists()).toBe(false)
  })

  it('a pointer-down inside the menu and a key other than Escape leave it open [T425]', async () => {
    const w = mountMenu()
    await open(w)
    w.get('.mc-item').element.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'a', bubbles: true }))
    await nextTick()
    expect(w.find('.map-context').exists()).toBe(true)
  })

  it('opening twice adds the document listeners once [T425]', async () => {
    const add = vi.spyOn(document, 'addEventListener')
    const w = mountMenu()
    await open(w)
    await open(w, { pixel: [30, 30] })
    const mine = (type) => add.mock.calls.filter((c) => c[0] === type && c[2] === true)
    expect(mine('pointerdown')).toHaveLength(1)
    expect(mine('keydown')).toHaveLength(1)
  })

  it('choosing an item calls onSelect with the coordinate and its lon/lat and closes the menu [T425]', async () => {
    const it1 = item()
    const w = mountMenu([it1])
    await open(w, { coordinate: [2451, 4251] })
    await w.get('[data-testid="item-one"]').trigger('click')
    expect(it1.onSelect).toHaveBeenCalledTimes(1)
    expect(it1.onSelect).toHaveBeenCalledWith({ coordinate: [2451, 4251], lonLat: [24.51, 42.51] })
    expect(w.find('.map-context').exists()).toBe(false)
  })

  it('an item whose onSelect throws is logged by id, the menu still closes and the other items stay usable [T425]', async () => {
    const bad = item({ id: 'bad', testId: 'bad', onSelect: vi.fn(() => { throw new Error('boom') }) })
    const good = item({ id: 'good', testId: 'good' })
    const w = mountMenu([bad, good])
    await open(w)
    await w.get('[data-testid="bad"]').trigger('click')
    const logged = errSpy.mock.calls.find((c) => c[0] === '[map-shell] context-menu item "%s" failed')
    expect(logged?.[1]).toBe('bad')
    expect(w.find('.map-context').exists()).toBe(false)
    await open(w)
    await w.get('[data-testid="good"]').trigger('click')
    expect(good.onSelect).toHaveBeenCalledTimes(1)
  })

  it('an onSelect that rejects is logged by id [T425]', async () => {
    const bad = item({ id: 'async-bad', onSelect: vi.fn(() => Promise.reject(new Error('later'))) })
    const w = mountMenu([bad])
    await open(w)
    await w.get('.mc-item').trigger('click')
    await Promise.resolve()
    await Promise.resolve()
    const logged = errSpy.mock.calls.find((c) => c[0] === '[map-shell] context-menu item "%s" failed')
    expect(logged?.[1]).toBe('async-bad')
  })

  it('a failing item logs the message and status, never the error object [B108]', async () => {
    const axiosLike = () => Object.assign(new Error('Request failed'), { config: { headers: { Authorization: 'Bearer SECRET-TOKEN-B108' } }, response: { status: 500 } })
    const sync = item({ id: 'sync', testId: 'sync', onSelect: vi.fn(() => { throw axiosLike() }) })
    const async_ = item({ id: 'async', testId: 'async', onSelect: vi.fn(() => Promise.reject(axiosLike())) })
    const w = mountMenu([sync, async_])
    for (const id of ['sync', 'async']) {
      errSpy.mockClear()
      await open(w)
      await w.get(`[data-testid="${id}"]`).trigger('click')
      await Promise.resolve()
      await Promise.resolve()
      expect(errSpy).toHaveBeenCalled()
      const args = errSpy.mock.calls.flat()
      expect(args.some((a) => a !== null && typeof a === 'object')).toBe(false)
      const text = args.join(' ')
      expect(text).not.toContain('SECRET-TOKEN-B108')
      expect(text).toContain(id)
      expect(text).toContain('Request failed')
      expect(text).toContain('HTTP 500')
    }
  })

  it('close() is idempotent and safe on a closed menu [T425]', async () => {
    const remove = vi.spyOn(document, 'removeEventListener')
    const w = mountMenu()
    w.vm.close()
    expect(remove).not.toHaveBeenCalledWith('pointerdown', expect.anything(), true)
    await open(w)
    w.vm.close()
    w.vm.close()
    expect(remove.mock.calls.filter((c) => c[0] === 'pointerdown' && c[2] === true)).toHaveLength(1)
  })

  it('unmount while open removes the document listeners; a mount, unmount, mount cycle never stacks them [T425]', async () => {
    const add = vi.spyOn(document, 'addEventListener')
    const remove = vi.spyOn(document, 'removeEventListener')
    const count = (spy, type) => spy.mock.calls.filter((c) => c[0] === type && c[2] === true).length
    for (let i = 0; i < 2; i++) {
      const w = mountMenu()
      await open(w)
      w.unmount()
      mounted.pop()
    }
    expect(count(add, 'pointerdown')).toBe(2)
    expect(count(remove, 'pointerdown')).toBe(2)
    expect(count(add, 'keydown')).toBe(2)
    expect(count(remove, 'keydown')).toBe(2)
    // a stale listener would reopen nothing, but a second mount must start clean
    const w = mountMenu()
    expect(w.find('.map-context').exists()).toBe(false)
  })

  it('items that go away while the menu is open close it [T425]', async () => {
    const w = mountMenu()
    await open(w)
    await w.setProps({ items: [] })
    expect(w.find('.map-context').exists()).toBe(false)
  })

  it('two items sharing an id log a problem naming the id [T425]', () => {
    mountMenu([item(), item({ testId: 'dup' })])
    expect(errSpy.mock.calls.map((c) => c.join(' ')).join('\n')).toContain('contextMenu: id "one" is used more than once')
  })
})
