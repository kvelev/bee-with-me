// The map shell: owns the OpenLayers map, the layer registry (z-order), the map "modes" (placing HQ,
// placing a repeater, measuring) and the dispatch of click, pointer-move and context-menu events.
// Plain JavaScript, no Vue. It is created at component set-up with no target and mounted later, so
// layers, handlers and modes registered before mount are in force when the map appears.
//
// Contributions (layers, handlers) arrive as arguments; the shell imports no module and no feature.
import OlMap from 'ol/Map'

const LONG_PRESS_MS = 600
const LONG_PRESS_SLOP_PX = 10
const CONTEXT_DEDUPE_MS = 800
const DEFAULT_ORDER = 100

// Stable insert: by `order`, ties in registration order.
function insertSorted(list, entry) {
  let i = list.length
  while (i > 0 && list[i - 1].order > entry.order) i -= 1
  list.splice(i, 0, entry)
}

export function createMapShell({ view, controls = [], overlays = [], createLongPress, modes = [], basemap = null } = {}) {
  let map = null
  let basemapLayer = basemap
  const layers = new Map()            // id -> layer, in registration order
  const active = new Set()            // modes that are on
  const clickHandlers = []            // { fn, mode, order }
  const moveHandlers = []             // { fn, mode, order, always }
  const mountedCallbacks = []
  const disposers = []
  let contextHandler = null
  let longPress = null
  let lastContextAt = -Infinity
  let viewportListeners = []

  function addLayer({ id, zIndex, layer }) {
    if (layers.has(id)) throw new Error(`map layer ${id} is already registered`)
    layer.setZIndex(zIndex)
    layers.set(id, layer)
    if (map) map.addLayer(layer)
  }

  function install(mapEntry, declarations, ctx) {
    const name = mapEntry?.name
    try {
      for (const d of declarations ?? []) {
        const factory = mapEntry.layers?.[d.id]
        if (typeof factory === 'function') addLayer({ id: d.id, zIndex: d.zIndex, layer: factory(ctx) })
      }
      const result = mapEntry.setup?.(shell, ctx)
      if (typeof result?.dispose === 'function') disposers.push(result.dispose)
      return result?.api ?? {}
    } catch (error) {
      console.error(`map contribution ${name} failed to install`, error)
      return {}
    }
  }

  function setMode(name, on) {
    if (!modes.includes(name)) throw new Error(`unknown map mode ${name}`)
    if (on) active.add(name)
    else active.delete(name)
    const target = map?.getTargetElement()
    if (target) target.style.cursor = on ? 'crosshair' : ''
  }

  function mode() {
    return modes.find((m) => active.has(m)) ?? null
  }

  function onClick(fn, { mode: forMode = null, order = DEFAULT_ORDER } = {}) {
    const entry = { fn, mode: forMode, order }
    insertSorted(clickHandlers, entry)
    return () => { const i = clickHandlers.indexOf(entry); if (i >= 0) clickHandlers.splice(i, 1) }
  }

  function onPointerMove(fn, { mode: forMode = null, order = DEFAULT_ORDER, always = false } = {}) {
    const entry = { fn, mode: forMode, order, always }
    insertSorted(moveHandlers, entry)
    return () => { const i = moveHandlers.indexOf(entry); if (i >= 0) moveHandlers.splice(i, 1) }
  }

  // Runs the handlers in order; a handler that returns true stops the ones after it, one that throws is
  // logged and skipped.
  function run(list, evt, what) {
    for (const { fn } of list) {
      try {
        if (fn(evt) === true) return
      } catch (error) {
        console.error(`map ${what} handler failed`, error)
      }
    }
  }

  function selectFor(handlers, current) {
    return handlers.filter((h) => (current === null ? h.mode === null : h.mode === current))
  }

  function dispatchClick(evt) {
    if (longPress?.shouldSwallowClick()) return
    run(selectFor(clickHandlers, mode()), evt, 'click')
  }

  function dispatchMove(evt) {
    if (evt.dragging) return
    const current = mode()
    const always = moveHandlers.filter((h) => h.always)
    const rest = selectFor(moveHandlers, current).filter((h) => !h.always)
    run([...always, ...rest], evt, 'pointer')
  }

  // The time of a report is recorded before the mode is looked at: an attempt in a mode still starts the
  // window, as before the shell existed.
  function reportContext(clientX, clientY) {
    const now = performance.now()
    if (now - lastContextAt < CONTEXT_DEDUPE_MS) return
    lastContextAt = now
    if (!contextHandler || mode() !== null || !map) return
    const pixel = map.getEventPixel({ clientX, clientY })
    const coordinate = map.getCoordinateFromPixel(pixel)
    if (coordinate) contextHandler({ coordinate, pixel })
  }

  function onContextMenu(handler) {
    contextHandler = handler
  }

  function onMounted(fn) {
    mountedCallbacks.push(fn)
  }

  function mount(target) {
    map = new OlMap({
      target,
      layers: [...(basemapLayer ? [basemapLayer] : []), ...layers.values()],
      view,
      overlays,
      controls,
    })
    map.on('pointermove', dispatchMove)
    map.on('click', dispatchClick)

    const viewport = map.getViewport()
    const onContextMenuEvent = (e) => { e.preventDefault(); reportContext(e.clientX, e.clientY) }
    longPress = createLongPress({ onLongPress: reportContext, ms: LONG_PRESS_MS, slopPx: LONG_PRESS_SLOP_PX })
    viewportListeners = [
      ['contextmenu', onContextMenuEvent],
      ['pointerdown', longPress.down],
      ['pointermove', longPress.move],
      ['pointerup', longPress.end],
      ['pointercancel', longPress.end],
    ]
    for (const [type, fn] of viewportListeners) viewport.addEventListener(type, fn)

    for (const fn of mountedCallbacks) {
      try { fn() } catch (error) { console.error('map onMounted callback failed', error) }
    }
  }

  // The basemap is the first layer of the map and is replaced in place. Before mount it does nothing.
  function setBasemap(layer) {
    if (!map) return
    map.getLayers().removeAt(0)
    basemapLayer = layer
    map.getLayers().insertAt(0, layer)
  }

  function dispose() {
    for (const fn of disposers.splice(0)) {
      try { fn() } catch (error) { console.error('map contribution dispose failed', error) }
    }
    if (map) {
      const viewport = map.getViewport()
      for (const [type, fn] of viewportListeners) viewport.removeEventListener(type, fn)
    }
    viewportListeners = []
    longPress?.end()
    map?.setTarget(null)
    map = null
  }

  const shell = {
    get map() { return map },
    addLayer,
    layer: (id) => layers.get(id),
    install,
    mount,
    setMode,
    mode,
    onClick,
    onPointerMove,
    onContextMenu,
    onMounted,
    setBasemap,
    dispose,
  }
  return shell
}
