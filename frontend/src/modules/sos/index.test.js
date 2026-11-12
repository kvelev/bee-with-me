import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { collectBanners, collectPanels, contributionProblems } from '../../platform/map-shell/contributions.js'
import { BANNER_PRIORITY } from '../../platform/map-shell/zorder.js'
import { checkModules } from '../../platform/registry.js'
import { MODULES } from '../index.js'
import sos from './index.js'
import { useSosStore } from './store.js'

describe('sos module manifest', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('SOS is a manifest banner at priority 10 and comes before the fire alarm [T544]', () => {
    expect(MODULES).toContain(sos)
    expect(BANNER_PRIORITY.sos).toBe(10)
    expect(sos.banners).toHaveLength(1)
    expect(sos.banners[0]).toMatchObject({ id: 'sos', priority: 10 })
    expect(collectBanners(MODULES).map((b) => b.id)).toEqual(['sos', 'fire-alarm'])
    expect(contributionProblems(MODULES)).toEqual([])
    expect(checkModules(MODULES)).toEqual([])
  })

  it('sos depends on tracking and imports it only through its index [T544]', () => {
    expect(sos.depends).toEqual(['tracking'])
    const dir = path.dirname(fileURLToPath(import.meta.url))
    const files = []
    const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).forEach((e) => {
      const p = path.join(d, e.name)
      if (e.isDirectory()) walk(p)
      else if (/\.(js|vue)$/.test(e.name) && !e.name.includes('.test.')) files.push(p)
    })
    walk(dir)
    const imports = files.flatMap((f) => [...fs.readFileSync(f, 'utf8').matchAll(/from '([^']*tracking[^']*)'/g)].map((m) => m[1]))
    expect(imports.length).toBeGreaterThan(0)
    expect(imports.every((i) => i === '../tracking/index.js')).toBe(true)
  })
  it('the toast is a map-root panel and MapView does not import it [T545]', () => {
    expect(sos.panels).toHaveLength(1)
    expect(sos.panels[0]).toMatchObject({ id: 'sos-toast', host: 'map-root', order: 10 })
    expect(collectPanels(MODULES, 'map-root').map((p) => p.id)).toContain('sos-toast')
    const dir = path.dirname(fileURLToPath(import.meta.url))
    const view = fs.readFileSync(path.join(dir, '../../views/MapView.vue'), 'utf8')
    expect(view).not.toMatch(/SOSToast/)
    expect(fs.existsSync(path.join(dir, '../../components/SOSToast.vue'))).toBe(false)
    const store = useSosStore()
    expect(sos.panels[0].retryKey()).toBe(0)
    store.sosNotifications.push({ id: 1, device_id: 'd', name: 'x', timestamp: 't' })
    expect(sos.panels[0].retryKey()).toBe(1)
  })
})
