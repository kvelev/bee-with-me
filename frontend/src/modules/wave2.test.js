import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../api', () => ({ getMe: vi.fn(), login: vi.fn() }))

import architecture from '../architecture.allowlist.json'
import { collectLiveHandlers } from '../platform/live/dispatch.js'
import {
  collectBanners, collectContextMenu, collectMapLayers, collectPopups, popupFor,
} from '../platform/map-shell/contributions'
import { MODULES } from './index.js'
import { staticOlChain } from './olScan.helper.js'

// What wave 2 reached, as lower bounds and membership only: later waves add modules, banners, layers and message
// types, so no exact list or count is asserted. The tracker panel and layers (T548, T549) are not merged and are
// not pinned here; the thin payload is pinned by the tests of T546 and T547.
const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

// The message types the backend sends today: seven from module manifests, `serial_status` from the gateway reader.
const LIVE_TYPES = [
  'location_update', 'serial_status', 'sos_alert',
  'fire_data_updated', 'fire_zones_updated', 'fire_alert', 'fire_alert_repeat', 'fire_alert_updated',
]

const isTest = (file) => /\.test\.js$|\.helper\.js$/.test(file) || file.includes(`${path.sep}__tests__${path.sep}`)

function sourceFiles(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) return sourceFiles(full)
    return /\.(js|vue|css|json)$/.test(entry.name) && !isTest(full) ? [full] : []
  })
}

describe('the state after wave 2', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('fire, sos, tracking and weather are modules [T590]', () => {
    const names = MODULES.map((m) => m.name)
    for (const name of ['fire', 'sos', 'tracking', 'weather']) expect(names).toContain(name)
  })

  it('the banners are SOS then the fire alarm and no legacy list exists [T590]', () => {
    const ids = collectBanners(MODULES).map((b) => b.id)
    expect(ids).toContain('fire-alarm')
    expect(ids[0]).toBe('sos')
    expect(ids.indexOf('sos')).toBeLessThan(ids.indexOf('fire-alarm'))
    expect(fs.existsSync(path.join(SRC, 'components', 'legacyBanners.js'))).toBe(false)
    expect(fs.existsSync(path.join(SRC, 'composables', 'legacyLive.js'))).toBe(false)
  })

  it('the fire layers, popup and menu item come from the manifest [T590]', () => {
    const layers = collectMapLayers(MODULES).map((l) => l.id)
    for (const id of ['fire-burnt', 'fire-zones', 'fire-hotspots']) expect(layers).toContain(id)
    expect(popupFor(collectPopups(MODULES), 'hotspot')).not.toBeNull()
    expect(collectContextMenu(MODULES).map((i) => i.id)).toContain('fire-report-here')
  })

  it('no source file still says until step 2 [T590]', () => {
    const files = sourceFiles(SRC)
    expect(files.length).toBeGreaterThan(50)
    const hits = files.filter((f) => /until step 2\b/i.test(fs.readFileSync(f, 'utf8')))
    expect(hits.map((f) => path.relative(SRC, f))).toEqual([])
  })

  it('every live message type has a manifest handler [T590]', () => {
    const handlers = collectLiveHandlers(MODULES)
    for (const type of LIVE_TYPES) {
      expect(handlers.get(type)?.length ?? 0, type).toBeGreaterThanOrEqual(1)
      for (const fn of handlers.get(type)) expect(fn, type).toBeTypeOf('function')
    }
  })

  it('no manifest reaches OpenLayers [T590]', () => {
    const dir = path.join(SRC, 'modules')
    const manifests = fs.readdirSync(dir, { withFileTypes: true })
      .filter((d) => d.isDirectory())
      .map((d) => path.join(dir, d.name, 'index.js'))
      .filter((f) => fs.existsSync(f))
    expect(manifests.length).toBeGreaterThanOrEqual(8)
    for (const file of manifests) expect(staticOlChain(file), file).toBeNull()
  })

  it('the frontend step is recorded [T590]', () => {
    expect(architecture.completed_step).toBeGreaterThanOrEqual(2)
  })
})
