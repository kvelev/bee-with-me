import { describe, it, expect, vi, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { h, reactive } from 'vue'
import PanelHost from './PanelHost.vue'

const stub = (cls) => ({ props: ['context'], render() { return h('div', { class: cls, 'data-who': this.context?.who }) } })
const boom = () => ({ props: ['context'], render() { throw new Error('boom') } })

afterEach(() => { vi.restoreAllMocks() })

describe('PanelHost', () => {
  it('renders the panels in order without a wrapper and hands each the context [T504]', () => {
    const host = document.createElement('div')
    mount(PanelHost, {
      attachTo: host,
      props: {
        panels: [{ id: 'a', component: stub('a') }, { id: 'b', component: stub('b') }],
        context: { who: 'ctx' },
      },
    })
    const kids = [...host.firstElementChild.children]
    expect(kids.map((e) => e.className)).toEqual(['a', 'b'])
    expect(kids.map((e) => e.getAttribute('data-who'))).toEqual(['ctx', 'ctx'])
    expect(host.firstElementChild.className).not.toContain('panel-host')
  })

  it('a panel that throws is skipped and logged once, the others stay [T504]', async () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    const ctx = reactive({ who: 'x' })
    const host = document.createElement('div')
    const w = mount(PanelHost, {
      attachTo: host,
      props: { panels: [{ id: 'a', component: stub('a') }, { id: 'bad', component: boom() }, { id: 'c', component: stub('c') }], context: ctx },
    })
    await flushPromises()
    ctx.who = 'y'
    await flushPromises()
    expect([...host.firstElementChild.children].map((e) => e.className)).toEqual(['a', 'c'])
    const mine = err.mock.calls.filter((c) => String(c[0]).startsWith('panel bad failed'))
    expect(mine).toHaveLength(1)
    expect(mine[0][1]).toBe('boom')   // the message text, never the error object [B108]
    w.unmount()
  })

  it('an empty list renders nothing [T504]', () => {
    const w = mount(PanelHost, { props: { panels: [], context: {} } })
    expect(w.html()).toBe('<!---->')
  })

  it('a failed panel with a retryKey is rendered again when the key changes, one without it is not [T504]', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const ctx = reactive({ n: 0, fail: true })
    const flaky = (cls) => ({ props: ['context'], render() { if (this.context.fail) throw new Error('flaky'); return h('div', { class: cls }) } })
    const host = document.createElement('div')
    mount(PanelHost, {
      attachTo: host,
      props: {
        panels: [
          { id: 'retry', component: flaky('retry'), retryKey: (c) => c.n },
          { id: 'plain', component: flaky('plain') },
        ],
        context: ctx,
      },
    })
    await flushPromises()
    expect(host.firstElementChild?.children.length ?? 0).toBe(0)
    ctx.fail = false
    await flushPromises()
    expect(host.querySelector('.retry')).toBeNull()      // no key change yet: still away
    ctx.n = 1
    await flushPromises()
    expect(host.querySelector('.retry')).not.toBeNull()
    expect(host.querySelector('.plain')).toBeNull()      // never retried without a retryKey
  })

  it('a retryKey that throws does not stop the panel from being retried later [T504]', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const ctx = reactive({ n: 0, fail: true, broken: true })
    const flaky = { props: ['context'], render() { if (this.context.fail) throw new Error('flaky'); return h('div', { class: 'p' }) } }
    const host = document.createElement('div')
    mount(PanelHost, {
      attachTo: host,
      props: { panels: [{ id: 'p', component: flaky, retryKey: (c) => { if (c.broken) throw new Error('key'); return c.n } }], context: ctx },
    })
    await flushPromises()
    expect(host.querySelector('.p')).toBeNull()
    ctx.fail = false
    ctx.broken = false
    await flushPromises()
    ctx.n = 1
    await flushPromises()
    expect(host.querySelector('.p')).not.toBeNull()
  })

  describe('logs carry the message and status, never the error object [B108]', () => {
    const axiosLike = () => Object.assign(new Error('Request failed'), { config: { headers: { Authorization: 'Bearer SECRET-TOKEN-B108' } }, response: { status: 500 } })
    const expectSafe = (err) => {
      expect(err).toHaveBeenCalled()
      const args = err.mock.calls.flat()
      expect(args.some((a) => a !== null && typeof a === 'object')).toBe(false)
      const text = args.join(' ')
      expect(text).not.toContain('SECRET-TOKEN-B108')
      expect(text).toContain('Request failed')
      expect(text).toContain('HTTP 500')
    }

    it('a panel that fails to render [B108]', async () => {
      const err = vi.spyOn(console, 'error').mockImplementation(() => {})
      const bad = { props: ['context'], render() { throw axiosLike() } }
      mount(PanelHost, { props: { panels: [{ id: 'bad', component: bad }], context: {} } })
      await flushPromises()
      expectSafe(err)
      expect(err.mock.calls[0][0]).toContain('panel bad failed')
    })

    it('a retryKey that throws [B108]', async () => {
      const err = vi.spyOn(console, 'error').mockImplementation(() => {})
      mount(PanelHost, { props: { panels: [{ id: 'k', component: stub('k'), retryKey: () => { throw axiosLike() } }], context: {} } })
      await flushPromises()
      expectSafe(err)
      expect(err.mock.calls[0][0]).toContain('panel k retryKey failed')
    })
  })
})
