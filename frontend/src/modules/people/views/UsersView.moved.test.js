import fs from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import manifest from '../index.js'

const here = (p) => fileURLToPath(new URL(p, import.meta.url))

describe('UsersView location', () => {
  it('the people route loads the view from the module [T441]', async () => {
    const mod = await manifest.routes[0].component()
    expect(mod.default.__name).toBe('UsersView')
    expect(fs.existsSync(here('../../../views/UsersView.vue'))).toBe(false)
    expect(fs.existsSync(here('./UsersView.vue'))).toBe(true)
  })
})
