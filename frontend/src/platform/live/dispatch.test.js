// @vitest-environment node
import { afterEach, describe, expect, it, vi } from 'vitest'
import { collectLiveHandlers, collectLiveHooks, dispatchLive, runHooks, runSetup } from './dispatch.js'

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
    expect(err).toHaveBeenCalledWith('live handler ping failed: boom')
  })

  it('a handler whose promise rejects is logged [T543]', async () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    const boom = new Error('late')
    const handlers = collectLiveHandlers([mod({ ping: () => Promise.reject(boom) })])
    dispatchLive(handlers, { type: 'ping' })
    await Promise.resolve(); await Promise.resolve()
    expect(err).toHaveBeenCalledWith('live handler ping failed: late')
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

  it('an axios-like error is logged as message and status only, the bearer token never reaches the console [B99]', async () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    const axiosLike = Object.assign(new Error('Request failed with status code 500'), {
      config: { headers: { Authorization: 'Bearer SECRET-TOKEN' } },
      response: { status: 500 },
    })
    const handlers = collectLiveHandlers([mod({ ping: () => { throw axiosLike }, pong: () => Promise.reject(axiosLike) })])
    dispatchLive(handlers, { type: 'ping' })
    dispatchLive(handlers, { type: 'pong' })
    await Promise.resolve(); await Promise.resolve()
    expect(err).toHaveBeenCalledTimes(2)
    for (const args of err.mock.calls) {
      expect(args).toHaveLength(1)
      expect(typeof args[0]).toBe('string')
      expect(args[0]).toContain('500')
      expect(JSON.stringify(args)).not.toContain('SECRET-TOKEN')
    }
  })

  it('a rejected async handler is logged and the later handlers of that message still run [T590]', async () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    const later = vi.fn()
    const handlers = collectLiveHandlers([mod({ ping: () => Promise.reject(new Error('nope')) }), mod({ ping: later })], [{ type: 'ping', handler: later }])
    dispatchLive(handlers, { type: 'ping' })
    expect(later).toHaveBeenCalledTimes(2)
    await Promise.resolve(); await Promise.resolve()
    expect(err).toHaveBeenCalledWith('live handler ping failed: nope')
  })

  it('runSetup logs a throwing and a rejecting setup hook and runs the rest [B98]', async () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    const last = vi.fn()
    runSetup([() => { throw new Error('sync') }, () => Promise.reject(new Error('async')), last])
    await Promise.resolve(); await Promise.resolve()
    expect(last).toHaveBeenCalledTimes(1)
    expect(err).toHaveBeenCalledWith('live handler setup failed: sync')
    expect(err).toHaveBeenCalledWith('live handler setup failed: async')
  })
})
