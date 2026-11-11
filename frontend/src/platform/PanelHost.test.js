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
    expect(mine[0][1]).toBeInstanceOf(Error)
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
})
