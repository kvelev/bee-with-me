// @vitest-environment node
import { afterEach, describe, expect, it, vi } from 'vitest'
import { collectLiveHandlers, collectLiveHooks, dispatchLive, runHooks } from './dispatch.js'

const mod = (liveHandlers = {}, live) => ({ name: 'm', liveHandlers, ...(live ? { live } : {}) })

afterEach(() => { vi.restoreAllMocks() })

describe('live dispatch', () => {
  it('handlers of one type run in manifest order, then legacy [T543]', () => {
    const calls = []
    const modules = [
      mod({ ping: () => calls.push('a') }),
      mod({ ping: () => calls.push('b'), other: () => calls.push('x') }),
    ]
    const handlers = collectLiveHandlers(modules, [{ type: 'ping', handler: () => calls.push('legacy') }])
    dispatchLive(handlers, { type: 'ping' })
    expect(calls).toEqual(['a', 'b', 'legacy'])
  })

  it('a handler that throws is logged and the next one runs [T543]', () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    const boom = new Error('boom')
    const next = vi.fn()
    const handlers = collectLiveHandlers([mod({ ping: () => { throw boom } }), mod({ ping: next })])
    expect(() => dispatchLive(handlers, { type: 'ping' })).not.toThrow()
    expect(next).toHaveBeenCalledTimes(1)
    expect(err).toHaveBeenCalledWith('live handler ping failed', boom)
  })

  it('a handler whose promise rejects is logged [T543]', async () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    const boom = new Error('late')
    const handlers = collectLiveHandlers([mod({ ping: () => Promise.reject(boom) })])
    dispatchLive(handlers, { type: 'ping' })
    await Promise.resolve(); await Promise.resolve()
    expect(err).toHaveBeenCalledWith('live handler ping failed', boom)
  })

  it('an unknown type calls nobody [T543]', () => {
    const fn = vi.fn()
    const handlers = collectLiveHandlers([mod({ ping: fn })])
    expect(() => dispatchLive(handlers, { type: 'nope' })).not.toThrow()
    expect(fn).not.toHaveBeenCalled()
  })

  it('hooks are collected per kind and a failing hook does not stop the others [T543]', async () => {
    const calls = []
    const modules = [
      mod({}, { onTick: () => { calls.push('t1'); throw new Error('sync') }, onReconnect: () => calls.push('r1') }),
      mod({}, { onTick: () => { calls.push('t2'); return Promise.reject(new Error('async')) } }),
    ]
    const hooks = collectLiveHooks(modules, { onTick: [() => calls.push('t-legacy')], onReconnect: [() => calls.push('r-legacy')] })
    expect(hooks.onTick).toHaveLength(3)
    expect(hooks.onReconnect).toHaveLength(2)
    expect(hooks.setup).toHaveLength(0)
    await expect(runHooks(hooks.onTick)).resolves.toBeUndefined()
    expect(calls).toEqual(['t1', 't2', 't-legacy'])
    await runHooks(hooks.onReconnect)
    expect(calls.slice(3)).toEqual(['r1', 'r-legacy'])
  })

  it('setup hooks are collected in list order [T543]', () => {
    const a = () => {}; const b = () => {}; const c = () => {}
    const hooks = collectLiveHooks([mod({}, { setup: a }), mod({}), mod({}, { setup: b })], { setup: [c] })
    expect(hooks.setup).toEqual([a, b, c])
  })
})
