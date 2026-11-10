import fs from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import manifest from '../index.js'

const here = (p) => fileURLToPath(new URL(p, import.meta.url))

describe('GroupsView location', () => {
  it('the teams route loads the view from the module [T442]', async () => {
    const route = manifest.routes.find((r) => r.name === 'groups')
    expect(route.path).toBe('/groups')
    const mod = await route.component()
    expect(mod.default.__name).toBe('GroupsView')
    expect(fs.existsSync(here('../../../views/GroupsView.vue'))).toBe(false)
    expect(fs.existsSync(here('./GroupsView.vue'))).toBe(true)
  })
})
