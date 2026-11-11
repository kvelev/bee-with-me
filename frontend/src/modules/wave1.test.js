import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../api', () => ({ getMe: vi.fn(), login: vi.fn() }))

import architecture from '../architecture.allowlist.json'
import { collectMapLayers } from '../platform/map-shell/contributions'
import router from '../router/index.js'
import { MODULES } from './index.js'
import { staticOlChain } from './olScan.helper.js'

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

  it('the four pages are served by module routes [T460] [T582]', () => {
    // The layout is the route at '/' that has children; it is found by its component, not by a depth or a name.
    const layout = router.options.routes.find((r) => r.path === '/' && r.children?.length)
    expect(layout?.component).toBeTypeOf('function')
    for (const [url, name] of [['/settings', 'settings'], ['/users', 'users'], ['/groups', 'groups'], ['/devices', 'devices']]) {
      const to = router.resolve(url)
      expect(to.matched.at(-1).name, url).toBe(name)
      expect(to.name, url).toBe(name)
      expect(to.matched.some((r) => r.components?.default === layout.component), url).toBe(true)
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

  it('no manifest imports OpenLayers, directly or through what it imports [T460] [T582]', () => {
    const dir = path.join(SRC, 'modules')
    const manifests = fs.readdirSync(dir, { withFileTypes: true })
      .filter((d) => d.isDirectory())
      .map((d) => path.join(dir, d.name, 'index.js'))
      .filter((f) => fs.existsSync(f))
    expect(manifests.length).toBeGreaterThanOrEqual(4)
    for (const file of manifests) expect(staticOlChain(file), file).toBeNull()
  })

  it('the OpenLayers scan sees a side-effect import and an import behind a helper [T582]', () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wave1-ol-'))
    try {
      const write = (rel, body) => {
        const file = path.join(root, rel)
        fs.mkdirSync(path.dirname(file), { recursive: true })
        fs.writeFileSync(file, body)
      }
      write('a/index.js', "import 'ol/ol.css'\nexport default {}\n")
      write('b/index.js', "import { make } from './helper.js'\nexport default make\n")
      write('b/helper.js', "import Map from 'ol/Map'\nexport const make = () => new Map()\n")
      write('c/index.js', "export default { layer: () => import('ol/Map') }\n")
      // the case the panels of wave 2 depend on: a manifest reaching a .vue file whose script imports OpenLayers
      write('d/index.js', "import Panel from './Panel.vue'\nexport default Panel\n")
      write('d/Panel.vue', "<template><div>import 'ol/Map'</div></template>\n<script setup>\nimport Overlay from 'ol/Overlay'\nconst o = Overlay\n</script>\n")
      write('e/index.js', "import Panel from './Panel.vue'\nexport default Panel\n")
      write('e/Panel.vue', "<template><div>import 'ol/Map'</div></template>\n<script setup>\nconst x = 1\n</script>\n")
      expect(staticOlChain(path.join(root, 'a/index.js'))).toEqual(['index.js', 'ol/ol.css'])
      expect(staticOlChain(path.join(root, 'b/index.js'))).toEqual(['index.js', 'helper.js', 'ol/Map'])
      expect(staticOlChain(path.join(root, 'c/index.js'))).toBeNull()
      expect(staticOlChain(path.join(root, 'd/index.js'))).toEqual(['index.js', 'Panel.vue', 'ol/Overlay'])
      expect(staticOlChain(path.join(root, 'e/index.js'))).toBeNull() // text in a template is not an import
    } finally {
      fs.rmSync(root, { recursive: true, force: true })
    }
  })
})
