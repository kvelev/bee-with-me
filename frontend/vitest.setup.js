/**
 * Vitest environment shims.
 *
 * Node 22+ exposes its own experimental `localStorage` global, which is inert unless the
 * process was started with --localstorage-file. Vitest's jsdom environment skips keys that
 * already exist on globalThis, so jsdom's working implementation never lands and any module
 * touching localStorage at import time fails to collect.
 *
 * Install jsdom's implementation explicitly when the global is missing or non-functional.
 */
function usable(store) {
  try {
    store.setItem('__probe__', '1')
    store.removeItem('__probe__')
    return true
  } catch {
    return false
  }
}

if (typeof globalThis.localStorage === 'undefined' || !usable(globalThis.localStorage)) {
  const memory = new Map()
  const shim = {
    getItem: (k) => (memory.has(String(k)) ? memory.get(String(k)) : null),
    setItem: (k, v) => { memory.set(String(k), String(v)) },
    removeItem: (k) => { memory.delete(String(k)) },
    clear: () => { memory.clear() },
    key: (i) => [...memory.keys()][i] ?? null,
    get length() { return memory.size },
  }
  Object.defineProperty(globalThis, 'localStorage', {
    value: shim, writable: true, configurable: true,
  })
}
