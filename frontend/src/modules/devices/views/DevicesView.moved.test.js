import fs from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import manifest from '../index.js'

const here = (p) => fileURLToPath(new URL(p, import.meta.url))

describe('DevicesView location', () => {
  it('the devices route loads the view from the module [T443]', async () => {
    const mod = await manifest.routes[0].component()
    expect(mod.default.__name).toBe('DevicesView')
    expect(fs.existsSync(here('../../../views/DevicesView.vue'))).toBe(false)
    expect(fs.existsSync(here('./DevicesView.vue'))).toBe(true)
  })
})
