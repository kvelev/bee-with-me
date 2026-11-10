import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../api', () => ({ getMe: vi.fn(), login: vi.fn() }))

import architecture from '../architecture.allowlist.json'
import { collectMapLayers } from '../platform/map-shell/contributions'
import router from '../router/index.js'
import { MODULES } from './index.js'

// What wave 1 reached, as lower bounds and membership only: step 2 adds `fire` to MODULES, so no exact list or
// count is asserted. `lib/groups.js` stays in place (it repairs position rows: tracking), so it is not listed below.
const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

describe('the state after wave 1', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('token', 'x')
    setActivePinia(createPinia())
  })

  it('devices, people, settings and teams are modules [T460]', () => {
    const names = MODULES.map((m) => m.name)
    for (const name of ['devices', 'people', 'settings', 'teams']) expect(names).toContain(name)
  })

  it('the four pages are served by module routes [T460]', () => {
    for (const [url, name] of [['/settings', 'settings'], ['/users', 'users'], ['/groups', 'groups'], ['/devices', 'devices']]) {
      const to = router.resolve(url)
      expect(to.name).toBe(name)
      expect(to.matched).toHaveLength(2)
      expect(to.matched[0].path).toBe('/') // under the layout
    }
    expect(router.resolve('/settings').meta.adminOnly).toBe(true)
  })

  it('src/views holds no moved view [T460]', () => {
    for (const file of ['SettingsView.vue', 'UsersView.vue', 'GroupsView.vue', 'DevicesView.vue']) {
      expect(fs.existsSync(path.join(SRC, 'views', file)), file).toBe(false)
    }
  })

  it('the frontend step is recorded [T460]', () => {
    expect(architecture.completed_step).toBeGreaterThanOrEqual(1)
  })

  it('the HQ layer comes from the settings module [T460]', () => {
    expect(collectMapLayers(MODULES).map((l) => l.id)).toContain('settings-hq')
  })

  it('no manifest imports OpenLayers [T460]', () => {
    const dir = path.join(SRC, 'modules')
    const manifests = fs.readdirSync(dir, { withFileTypes: true })
      .filter((d) => d.isDirectory())
      .map((d) => path.join(dir, d.name, 'index.js'))
      .filter((f) => fs.existsSync(f))
    expect(manifests.length).toBeGreaterThanOrEqual(4)
    for (const file of manifests) expect(fs.readFileSync(file, 'utf8'), file).not.toMatch(/from\s+['"]ol[/'"]/)
  })
})
