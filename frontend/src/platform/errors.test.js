import { describe, it, expect, vi, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { h, createApp } from 'vue'
import mainSource from '../main.js?raw'
import { installErrorHandlers } from './errors.js'
import PanelHost from './PanelHost.vue'

afterEach(() => { vi.restoreAllMocks() })

const rejection = (reason) => ({ reason, preventDefault: vi.fn() })

describe('installErrorHandlers', () => {
  it('a render error of a component outside any boundary is logged as one string [T634]', async () => {
    const log = vi.fn()
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const Bad = { setup() { throw new Error('kaboom') }, render() { return h('div') } }
    const app = createApp(Bad)
    installErrorHandlers(app, { target: new EventTarget(), log })
    app.mount(document.createElement('div'))
    await flushPromises()
    expect(log).toHaveBeenCalledTimes(1)
    expect(typeof log.mock.calls[0][0]).toBe('string')
    expect(log.mock.calls[0][0].startsWith('[app] ')).toBe(true)
    expect(log.mock.calls[0]).toHaveLength(1)
    app.unmount()
  })

  it('the log line of an axios-like error has the message and the status and no token [T634]', () => {
    const log = vi.fn()
    const app = { config: {} }
    installErrorHandlers(app, { target: new EventTarget(), log })
    const err = Object.assign(new Error('Request failed'), {
      response: { status: 500 },
      config: { headers: { Authorization: 'Bearer secret' } },
    })
    app.config.errorHandler(err, null, 'setup function')
    const line = log.mock.calls[0][0]
    expect(line).toContain('HTTP 500')
    expect(line).toContain('Request failed')
    expect(line).not.toContain('secret')
  })

  it('an unhandled rejection is logged as a string and its default is prevented [T634]', () => {
    const log = vi.fn()
    const target = new EventTarget()
    installErrorHandlers({ config: {} }, { target, log })
    const ev = Object.assign(new Event('unhandledrejection'), rejection(new Error('nope')))
    target.dispatchEvent(ev)
    expect(log).toHaveBeenCalledTimes(1)
    expect(log.mock.calls[0][0]).toBe('[app] unhandled rejection: nope')
    expect(ev.preventDefault).toHaveBeenCalledTimes(1)
  })

  it('a rejection whose reason is not an error is described [T634]', () => {
    const log = vi.fn()
    const target = new EventTarget()
    installErrorHandlers({ config: {} }, { target, log })
    for (const reason of ['x', undefined]) {
      target.dispatchEvent(Object.assign(new Event('unhandledrejection'), rejection(reason)))
    }
    expect(log).toHaveBeenCalledTimes(2)
    expect(log.mock.calls[0][0]).toBe('[app] unhandled rejection: x')
    expect(log.mock.calls[1][0]).toBe('[app] unhandled rejection: undefined')
  })

  it('the returned function removes the listener [T634]', () => {
    const log = vi.fn()
    const target = new EventTarget()
    const off = installErrorHandlers({ config: {} }, { target, log })
    off()
    target.dispatchEvent(Object.assign(new Event('unhandledrejection'), rejection(new Error('late'))))
    expect(log).not.toHaveBeenCalled()
  })

  it('a handler that cannot describe the error still logs one line [T634]', () => {
    const log = vi.fn()
    const app = { config: {} }
    const target = new EventTarget()
    installErrorHandlers(app, { target, log })
    const hostile = { get message() { throw new Error('getter') } }
    expect(() => app.config.errorHandler(hostile, null, 'render function')).not.toThrow()
    target.dispatchEvent(Object.assign(new Event('unhandledrejection'), rejection(hostile)))
    expect(log).toHaveBeenCalledTimes(2)
    expect(log.mock.calls[0][0]).toBe('[app] error (no description)')
    expect(log.mock.calls[1][0]).toBe('[app] error (no description)')
  })

  it('main.js installs the handlers before it mounts [T634]', () => {
    const text = mainSource
    const install = text.indexOf('installErrorHandlers(app)')
    expect(install).toBeGreaterThan(-1)
    expect(install).toBeLessThan(text.indexOf("app.mount('#app')"))
  })

  it('an error inside a panel boundary does not reach the global handler [T634]', async () => {
    const log = vi.fn()
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    const boom = { props: ['context'], render() { throw new Error('boom') } }
    const w = mount(PanelHost, {
      props: { panels: [{ id: 'bad', component: boom }] },
      global: { plugins: [{ install(app) { installErrorHandlers(app, { target: new EventTarget(), log }) } }] },
    })
    await flushPromises()
    expect(log).not.toHaveBeenCalled()
    expect(consoleError.mock.calls.some((c) => String(c[0]).startsWith('panel bad failed'))).toBe(true)
    w.unmount()
  })

  it('an uncaught error event of the window is logged as a string and its default is prevented [B147]', () => {
    const log = vi.fn()
    const target = new EventTarget()
    const off = installErrorHandlers({ config: {} }, { target, log })
    const err = Object.assign(new Error('script broke'), { config: { headers: { Authorization: 'Bearer secret' } } })
    const ev = Object.assign(new Event('error'), { error: err, message: 'Uncaught Error: script broke', preventDefault: vi.fn() })
    target.dispatchEvent(ev)
    expect(log).toHaveBeenCalledTimes(1)
    expect(log.mock.calls[0][0]).toBe('[app] uncaught error: script broke')
    expect(log.mock.calls[0][0]).not.toContain('secret')
    expect(ev.preventDefault).toHaveBeenCalledTimes(1)
    // an error event without an error object (a cross-origin script) is described by its message
    target.dispatchEvent(Object.assign(new Event('error'), { error: null, message: 'Script error.', preventDefault: vi.fn() }))
    expect(log.mock.calls[1][0]).toBe('[app] uncaught error: Script error.')
    off()
    target.dispatchEvent(Object.assign(new Event('error'), { error: err, preventDefault: vi.fn() }))
    expect(log).toHaveBeenCalledTimes(2)
  })
})
