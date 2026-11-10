import { describe, it, expect, vi, afterEach } from 'vitest'
import View from 'ol/View'
import TileLayer from 'ol/layer/Tile'
import VectorLayer from 'ol/layer/Vector'
import VectorSource from 'ol/source/Vector'
import { createMapShell } from './createMapShell.js'

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} }

const MODES = ['hq-place', 'repeater-place', 'measure']
const COORD = [100, 200]
const PIXEL = [5, 5]

afterEach(() => {
  document.body.innerHTML = ''
  vi.useRealTimers()
  vi.restoreAllMocks()
})

function make({ swallow = () => false, basemap } = {}) {
  const press = { opts: null, end: vi.fn() }
  const createLongPress = (opts) => {
    press.opts = opts
    return { down: vi.fn(), move: vi.fn(), end: press.end, shouldSwallowClick: () => swallow() }
  }
  const shell = createMapShell({ view: new View({ center: [0, 0], zoom: 3 }), controls: [], overlays: [], createLongPress, modes: MODES, basemap })
  const el = document.createElement('div')
  document.body.append(el)
  const layer = () => new VectorLayer({ source: new VectorSource() })
  const click = () => shell.map.dispatchEvent({ type: 'click', pixel: PIXEL, coordinate: COORD, originalEvent: {} })
  const move = (dragging = false) => shell.map.dispatchEvent({ type: 'pointermove', pixel: PIXEL, coordinate: COORD, dragging, originalEvent: {} })
  const rightClick = () => {
    const e = new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 5, clientY: 5 })
    shell.map.getViewport().dispatchEvent(e)
    return e
  }
  const stubPixels = () => {
    shell.map.getEventPixel = () => PIXEL
    shell.map.getCoordinateFromPixel = () => COORD
  }
  return { shell, el, press, layer, click, move, rightClick, stubPixels }
}

describe('createMapShell layers', () => {
  it('layers registered before mount are on the map after mount with their z-index, and a duplicate id throws [T422]', () => {
    const t = make()
    const a = t.layer()
    const b = t.layer()
    t.shell.addLayer({ id: 'a', zIndex: 3.5, layer: a })
    t.shell.addLayer({ id: 'b', zIndex: 10, layer: b })
    expect(t.shell.map).toBeNull()
    expect(t.shell.layer('a')).toBe(a)
    expect(t.shell.layer('nope')).toBeUndefined()
    expect(() => t.shell.addLayer({ id: 'a', zIndex: 1, layer: t.layer() })).toThrow('map layer a is already registered')
    t.shell.mount(t.el)
    expect(t.shell.map).not.toBeNull()
    expect(t.shell.map.getLayers().getArray()).toEqual([a, b])
    expect(a.getZIndex()).toBe(3.5)
    expect(b.getZIndex()).toBe(10)
    const c = t.layer()
    t.shell.addLayer({ id: 'c', zIndex: 20, layer: c })              // after mount: on the map at once
    expect(t.shell.map.getLayers().getArray()).toEqual([a, b, c])
    expect(c.getZIndex()).toBe(20)
  })

  it('the basemap is the first layer, replaced in place, and replacing before mount does nothing [T422]', () => {
    const first = new TileLayer()
    const t = make({ basemap: first })
    const a = t.layer()
    t.shell.addLayer({ id: 'a', zIndex: 3, layer: a })
    t.shell.setBasemap(new TileLayer())                               // before mount: no effect
    t.shell.mount(t.el)
    expect(t.shell.map.getLayers().getArray()).toEqual([first, a])
    const next = new TileLayer()
    t.shell.setBasemap(next)
    expect(t.shell.map.getLayers().getArray()).toEqual([next, a])
  })

  it('install runs the factories of the declared layers and the setup, and returns its api, before mount [T422]', () => {
    const t = make()
    const ctx = { token: 1 }
    const factory = vi.fn(() => t.layer())
    const ignored = vi.fn(() => t.layer())
    const setup = vi.fn((shell, c) => ({ api: { ping: () => c.token }, dispose: vi.fn() }))
    const api = t.shell.install(
      { name: 'demo', layers: { 'demo-x': factory, 'demo-unused': ignored }, setup },
      [{ id: 'demo-x', zIndex: 7 }, { id: 'demo-undeclared', zIndex: 8 }],
      ctx,
    )
    expect(factory).toHaveBeenCalledWith(ctx)
    expect(ignored).not.toHaveBeenCalled()
    expect(setup).toHaveBeenCalledWith(t.shell, ctx)
    expect(api.ping()).toBe(1)
    expect(t.shell.layer('demo-x').getZIndex()).toBe(7)
    expect(t.shell.layer('demo-undeclared')).toBeUndefined()
    expect(t.shell.install({ name: 'bare' }, [], ctx)).toEqual({})
  })

  it('a contribution that throws in a factory or in setup is logged and the next one is still installed [T422]', () => {
    const t = make()
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    const boom = new Error('boom')
    const a = t.shell.install({ name: 'bad-factory', layers: { x: () => { throw boom } } }, [{ id: 'x', zIndex: 1 }], {})
    const b = t.shell.install({ name: 'bad-setup', setup: () => { throw boom } }, [], {})
    const c = t.shell.install({ name: 'good', layers: { y: () => t.layer() }, setup: () => ({ api: { ok: true } }) }, [{ id: 'y', zIndex: 2 }], {})
    expect(a).toEqual({})
    expect(b).toEqual({})
    expect(c).toEqual({ ok: true })
    expect(t.shell.layer('y')).toBeDefined()
    expect(err).toHaveBeenCalledTimes(2)
    expect(err.mock.calls[0][0]).toContain('bad-factory')
    expect(err.mock.calls[0][0]).toContain('failed to install')
    expect(err.mock.calls[0][1]).toBe(boom)
    expect(err.mock.calls[1][0]).toContain('bad-setup')
  })
})

describe('createMapShell modes and click dispatch', () => {
  it('mode handlers win over mode-less ones [T422]', () => {
    const t = make()
    const calls = []
    t.shell.onClick(() => { calls.push('plain') })
    t.shell.onClick(() => { calls.push('hq') }, { mode: 'hq-place' })
    t.shell.mount(t.el)
    t.click()
    expect(calls).toEqual(['plain'])
    t.shell.setMode('hq-place', true)
    t.click()
    expect(calls).toEqual(['plain', 'hq'])
    t.shell.setMode('hq-place', false)
    t.click()
    expect(calls).toEqual(['plain', 'hq', 'plain'])
  })

  it('with two modes on the first of the precedence list is the mode, and switching the other off changes nothing [T422]', () => {
    const t = make()
    const calls = []
    t.shell.onClick(() => { calls.push('hq') }, { mode: 'hq-place' })
    t.shell.onClick(() => { calls.push('measure') }, { mode: 'measure' })
    t.shell.mount(t.el)
    expect(t.shell.mode()).toBeNull()
    t.shell.setMode('measure', true)
    expect(t.shell.mode()).toBe('measure')
    t.shell.setMode('hq-place', true)
    expect(t.shell.mode()).toBe('hq-place')
    t.click()
    t.shell.setMode('measure', false)
    expect(t.shell.mode()).toBe('hq-place')
    t.click()
    expect(calls).toEqual(['hq', 'hq'])
    t.shell.setMode('hq-place', false)
    expect(t.shell.mode()).toBeNull()
  })

  it('setMode throws for an unknown name and sets the cursor only once mounted [T422]', () => {
    const t = make()
    expect(() => t.shell.setMode('fly', true)).toThrow()
    t.shell.setMode('measure', true)                                   // before mount: no element, no cursor
    t.shell.mount(t.el)
    expect(t.el.style.cursor).toBe('')
    t.shell.setMode('repeater-place', true)
    expect(t.el.style.cursor).toBe('crosshair')
    t.shell.setMode('repeater-place', false)
    expect(t.el.style.cursor).toBe('')
    expect(t.shell.mode()).toBe('measure')                              // set before mount, still in force
  })

  it('mode-less click handlers run in order and stop at the first that returns true [T422]', () => {
    const t = make()
    const calls = []
    t.shell.onClick(() => { calls.push(20) }, { order: 20 })
    t.shell.onClick(() => { calls.push(10); return true }, { order: 10 })
    t.shell.mount(t.el)
    t.click()
    expect(calls).toEqual([10])
    const t2 = make()
    const calls2 = []
    t2.shell.onClick(() => { calls2.push('b') }, { order: 5 })
    t2.shell.onClick(() => { calls2.push('a') }, { order: 5 })
    t2.shell.onClick(() => { calls2.push('first') }, { order: 1 })
    t2.shell.mount(t2.el)
    t2.click()
    expect(calls2).toEqual(['first', 'b', 'a'])                         // ties keep the registration order
  })

  it('a handler can be unsubscribed, also one registered before mount [T422]', () => {
    const t = make()
    const fn = vi.fn()
    const off = t.shell.onClick(fn)
    t.shell.mount(t.el)
    t.click()
    off()
    t.click()
    expect(fn).toHaveBeenCalledTimes(1)
  })

  it('a click after a long press reaches no handler [T422]', () => {
    let swallow = false
    const t = make({ swallow: () => swallow })
    const fn = vi.fn()
    t.shell.onClick(fn)
    t.shell.mount(t.el)
    swallow = true
    t.click()
    expect(fn).not.toHaveBeenCalled()
    swallow = false
    t.click()
    expect(fn).toHaveBeenCalledTimes(1)
  })

  it('a throwing click handler is logged and the next one runs [T422]', () => {
    const t = make()
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    const next = vi.fn()
    t.shell.onClick(() => { throw new Error('bad') }, { order: 1 })
    t.shell.onClick(next, { order: 2 })
    t.shell.mount(t.el)
    t.click()
    expect(next).toHaveBeenCalledTimes(1)
    expect(err).toHaveBeenCalledTimes(1)
  })
})

describe('createMapShell pointer dispatch', () => {
  it('always pointer handlers run before the others [T422]', () => {
    const t = make()
    const calls = []
    t.shell.onPointerMove(() => { calls.push('fire') }, { order: 1 })
    t.shell.onPointerMove(() => { calls.push('tooltip') }, { always: true, order: 50 })
    t.shell.mount(t.el)
    t.move()
    expect(calls).toEqual(['tooltip', 'fire'])
  })

  it('an always pointer handler runs in every mode and a plain one only without a mode [T422]', () => {
    const t = make()
    const always = vi.fn()
    const plain = vi.fn()
    const measure = vi.fn()
    t.shell.onPointerMove(always, { always: true })
    t.shell.onPointerMove(plain)
    t.shell.onPointerMove(measure, { mode: 'measure' })
    t.shell.mount(t.el)
    t.move()
    expect([always.mock.calls.length, plain.mock.calls.length, measure.mock.calls.length]).toEqual([1, 1, 0])
    t.shell.setMode('hq-place', true)
    t.move()
    expect([always.mock.calls.length, plain.mock.calls.length, measure.mock.calls.length]).toEqual([2, 1, 0])
    t.shell.setMode('measure', true)
    t.shell.setMode('hq-place', false)
    t.move()
    expect([always.mock.calls.length, plain.mock.calls.length, measure.mock.calls.length]).toEqual([3, 1, 1])
  })

  it('a drag move reaches no handler [T422]', () => {
    const t = make()
    const fn = vi.fn()
    t.shell.onPointerMove(fn, { always: true })
    t.shell.mount(t.el)
    t.move(true)
    expect(fn).not.toHaveBeenCalled()
  })
})

describe('createMapShell context menu', () => {
  it('the long press made by the given factory reports through the context-menu path [T422]', () => {
    const t = make()
    const handler = vi.fn()
    t.shell.onContextMenu(handler)
    t.shell.mount(t.el)
    t.stubPixels()
    expect(t.press.opts.ms).toBe(600)
    expect(t.press.opts.slopPx).toBe(10)
    t.press.opts.onLongPress(5, 5)
    expect(handler).toHaveBeenCalledWith({ coordinate: COORD, pixel: PIXEL })
  })

  it('the browser context menu is always prevented, and the report is once per gesture, not while a mode is active, and a report in a mode still starts the 800 ms window [T422]', () => {
    vi.useFakeTimers()
    const t = make()
    const handler = vi.fn()
    t.shell.onContextMenu(handler)
    t.shell.mount(t.el)
    t.stubPixels()
    expect(t.rightClick().defaultPrevented).toBe(true)
    expect(handler).toHaveBeenCalledTimes(1)
    vi.advanceTimersByTime(500)
    expect(t.rightClick().defaultPrevented).toBe(true)                  // prevented even when dropped
    expect(handler).toHaveBeenCalledTimes(1)
    vi.advanceTimersByTime(400)
    t.rightClick()
    expect(handler).toHaveBeenCalledTimes(2)

    vi.advanceTimersByTime(900)
    t.shell.setMode('measure', true)
    expect(t.rightClick().defaultPrevented).toBe(true)                  // prevented in a mode too
    expect(handler).toHaveBeenCalledTimes(2)
    t.shell.setMode('measure', false)
    vi.advanceTimersByTime(300)
    t.rightClick()
    expect(handler).toHaveBeenCalledTimes(2)                            // the attempt in the mode started the window
    vi.advanceTimersByTime(600)
    t.rightClick()
    expect(handler).toHaveBeenCalledTimes(3)
  })

  it('nothing is reported when the pixel has no coordinate [T422]', () => {
    const t = make()
    const handler = vi.fn()
    t.shell.onContextMenu(handler)
    t.shell.mount(t.el)
    t.shell.map.getEventPixel = () => PIXEL
    t.shell.map.getCoordinateFromPixel = () => null
    t.rightClick()
    expect(handler).not.toHaveBeenCalled()
  })
})

describe('createMapShell lifecycle', () => {
  it('onMounted callbacks run at mount and dispose removes the target and calls every dispose [T422]', () => {
    const t = make()
    const order = []
    const dispose = vi.fn()
    const dispose2 = vi.fn(() => { throw new Error('late') })
    vi.spyOn(console, 'error').mockImplementation(() => {})
    t.shell.onMounted(() => order.push('first'))
    t.shell.onMounted(() => order.push('second'))
    t.shell.install({ name: 'one', setup: () => ({ dispose }) }, [], {})
    t.shell.install({ name: 'two', setup: () => ({ dispose: dispose2 }) }, [], {})
    expect(order).toEqual([])
    t.shell.mount(t.el)
    expect(order).toEqual(['first', 'second'])
    const map = t.shell.map
    const setTarget = vi.spyOn(map, 'setTarget')
    t.shell.dispose()
    expect(setTarget).toHaveBeenCalledWith(null)
    expect(dispose).toHaveBeenCalledTimes(1)
    expect(dispose2).toHaveBeenCalledTimes(1)
    expect(t.press.end).toHaveBeenCalled()
    expect(t.shell.map).toBeNull()
    // the viewport listeners are gone: a right click on the old viewport reports nothing
    const handler = vi.fn()
    t.shell.onContextMenu(handler)
    const e = new MouseEvent('contextmenu', { bubbles: true, cancelable: true })
    map.getViewport().dispatchEvent(e)
    expect(e.defaultPrevented).toBe(false)
    expect(handler).not.toHaveBeenCalled()
  })

  it('dispose before mount is harmless [T422]', () => {
    const t = make()
    expect(() => t.shell.dispose()).not.toThrow()
    expect(t.shell.map).toBeNull()
  })
})
