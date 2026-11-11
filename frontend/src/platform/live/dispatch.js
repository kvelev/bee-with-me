// Live-message dispatch (vertical-slice step 2). Pure: imports nothing. The socket in
// composables/useWebSocket.js stays where it is; what it does with a message or a timer tick is
// read from the modules' contributions (`liveHandlers`, `live`) plus the `legacy` lists that hold
// what has not moved into a module yet.

const HOOK_KINDS = ['setup', 'onTick', 'onReconnect']

/** Message type -> handlers: manifest handlers in list order, then the legacy `{ type, handler }` items. */
export function collectLiveHandlers(modules, legacy = []) {
  const byType = new Map()
  const add = (type, fn) => {
    if (!byType.has(type)) byType.set(type, [])
    byType.get(type).push(fn)
  }
  for (const m of modules) {
    for (const [type, fn] of Object.entries(m.liveHandlers ?? {})) add(type, fn)
  }
  for (const { type, handler } of legacy) add(type, handler)
  return byType
}

/** `{ setup, onTick, onReconnect }` lists: each manifest's `live` in list order, then the legacy lists. */
export function collectLiveHooks(modules, legacy = {}) {
  const hooks = { setup: [], onTick: [], onReconnect: [] }
  for (const kind of HOOK_KINDS) {
    for (const m of modules) {
      const fn = m.live?.[kind]
      if (fn) hooks[kind].push(fn)
    }
    hooks[kind].push(...(legacy[kind] ?? []))
  }
  return hooks
}

// Message and HTTP status only: an axios error carries the request config, and with it the bearer token.
function describe(error) {
  const text = error?.message ?? String(error)
  const status = error?.response?.status
  return status ? `${text} (HTTP ${status})` : text
}

function report(type, error) {
  console.error(`live handler ${type} failed: ${describe(error)}`)
}

/** Run the `setup` hooks once: a throw or a rejected promise is logged, the next hook still runs. */
export function runSetup(list) {
  for (const fn of list) {
    try {
      const result = fn()
      if (result && typeof result.then === 'function') result.then(undefined, (e) => report('setup', e))
    } catch (e) {
      report('setup', e)
    }
  }
}

/** Run every handler of `msg.type`. A throw or a rejected promise is logged; the next handler still runs. */
export function dispatchLive(handlers, msg) {
  for (const fn of handlers.get(msg?.type) ?? []) {
    try {
      const result = fn(msg)
      if (result && typeof result.then === 'function') result.then(undefined, (e) => report(msg.type, e))
    } catch (e) {
      report(msg.type, e)
    }
  }
}

/** Run all hooks; none stops another and a failure is swallowed (the next tick tries again). */
export async function runHooks(list) {
  await Promise.all(list.map(async (fn) => {
    try { await fn() } catch { /* offline or backend restarting */ }
  }))
}
