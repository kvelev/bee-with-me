// @vitest-environment node
// Frontend architecture guard (T306). Rules live in frontend/.dependency-cruiser.cjs; today's violations are the
// ratchet allowlist in src/architecture.allowlist.json (keys `rule|from|to`). New violations fail, stale entries
// fail, and the list may not grow against the merge base.
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { cruise } from 'dependency-cruiser'
import extractDepcruiseConfig from 'dependency-cruiser/config-utl/extract-depcruise-config'
import { beforeAll, describe, expect, it } from 'vitest'
import { validateManifest } from './platform/manifest.js'

const FRONTEND = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const CONFIG = path.join(FRONTEND, '.dependency-cruiser.cjs')
const ALLOWLIST = path.join(FRONTEND, 'src', 'architecture.allowlist.json')
const SLOW = 120_000

async function cruiseTree(baseDir, targets = ['src']) {
  const config = await extractDepcruiseConfig(CONFIG)
  const result = await cruise(
    targets,
    { ...config.options, ruleSet: config, validate: true, baseDir },
  )
  return result.output
}

function violationKeys(output) {
  return output.summary.violations
    .filter((v) => v.rule.severity === 'error')
    .map((v) => `${v.rule.name}|${v.from}|${v.to}`.replaceAll('\\', '/'))
    .sort()
}

// The ratchet: the count may fall, never rise. `baseText` is the allowlist at the merge base (null if absent).
function ratchetVerdict(baseText, headKeys) {
  if (baseText === null) return { status: 'skip', reason: 'allowlist absent at the merge base (this is its introduction)' }
  const baseCount = JSON.parse(baseText).violations.length
  if (headKeys.length > baseCount) return { status: 'fail', reason: `allowlist grew from ${baseCount} to ${headKeys.length}` }
  return { status: 'pass', reason: `${headKeys.length} <= ${baseCount}` }
}

function git(args) {
  return execFileSync('git', args, { cwd: FRONTEND, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim()
}

function resolveMergeBase() {
  const refs = [process.env.ARCH_BASE_REF, 'upstream/develop', 'origin/develop'].filter(Boolean)
  for (const ref of refs) {
    try {
      return git(['merge-base', 'HEAD', ref])
    } catch {
      // try the next ref
    }
  }
  return null
}

function readAllowlist() {
  return JSON.parse(fs.readFileSync(ALLOWLIST, 'utf8'))
}

describe('frontend architecture', () => {
  let real

  beforeAll(async () => {
    real = await cruiseTree(FRONTEND)
  }, SLOW)

  it('real sources match the allowlist exactly [T306]', () => {
    const allowed = readAllowlist().violations
    const found = violationKeys(real)
    const fresh = found.filter((k) => !allowed.includes(k))
    const stale = allowed.filter((k) => !found.includes(k))
    const message = [
      fresh.length ? `NEW violations (fix the import, do not add to the allowlist):\n  ${fresh.join('\n  ')}` : '',
      stale.length ? `STALE allowlist entries (delete these lines):\n  ${stale.join('\n  ')}` : '',
    ].filter(Boolean).join('\n')
    expect(message).toBe('')
    expect(allowed).toEqual([...allowed].sort())
  })

  it('each rule bites on a fixture tree [T306]', async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'arch-fixture-'))
    const write = (rel, body) => {
      const file = path.join(root, rel)
      fs.mkdirSync(path.dirname(file), { recursive: true })
      fs.writeFileSync(file, body)
    }
    try {
      write('node_modules/vue/package.json', '{"name":"vue","version":"0.0.0","main":"index.js"}')
      write('node_modules/vue/index.js', 'module.exports = {}\n')
      write('src/stores/s.js', 'export default 1\n')
      write('src/views/v.js', 'export default 1\n')
      write('src/lib/a.js', "import s from '../stores/s.js'\nimport 'vue'\nexport default s\n")
      write('src/api/x.js', "import v from '../views/v.js'\nexport default v\n")
      write('src/components/c.js', "import v from '../views/v.js'\nexport default v\n")
      write('src/stores/p.js', "import q from './q.js'\nexport default q\n")
      write('src/stores/q.js', "import p from './p.js'\nexport default p\n")
      write('src/modules/m/index.js', 'export default 1\n')
      write('src/platform/p.js', "import m from '../modules/m/index.js'\nexport default m\n")
      write('src/modules/a/index.js', "import b from '../b/index.js'\nimport inner from '../b/internal.js'\nexport default [b, inner]\n")
      write('src/modules/b/index.js', 'export default 1\n')
      write('src/modules/b/internal.js', 'export default 1\n')

      const keys = violationKeys(await cruiseTree(root))
      const has = (rule, from, to) => expect(keys).toContain(`${rule}|${from}|${to}`)
      has('lib-is-pure', 'src/lib/a.js', 'src/stores/s.js')
      expect(keys.some((k) => k.startsWith('lib-is-pure|src/lib/a.js|') && k.includes('vue'))).toBe(true)
      has('no-upward-layers', 'src/api/x.js', 'src/views/v.js')
      has('no-upward-layers', 'src/components/c.js', 'src/views/v.js')
      has('no-circular', 'src/stores/p.js', 'src/stores/q.js')
      has('platform-imports-no-module', 'src/platform/p.js', 'src/modules/m/index.js')
      has('modules-only-through-index', 'src/modules/a/index.js', 'src/modules/b/internal.js')
      // the allowed edge (another module's index.js) must stay clean
      expect(keys).not.toContain('modules-only-through-index|src/modules/a/index.js|src/modules/b/index.js')
    } finally {
      fs.rmSync(root, { recursive: true, force: true })
    }
  }, SLOW)

  it('single-file components are cruised [T306]', () => {
    // If @vue/compiler-sfc is missing the cruiser silently skips .vue content: fail loudly instead.
    const mapView = real.modules.find((m) => m.source === 'src/views/MapView.vue')
    expect(mapView, 'src/views/MapView.vue was not cruised (is @vue/compiler-sfc installed?)').toBeDefined()
    expect(mapView.dependencies.map((d) => d.resolved)).toContain('src/composables/useMap.js')
    expect(real.modules.length).toBeGreaterThan(60)
  })

  it('manifest validator accepts a complete manifest and names each missing field [T306]', () => {
    const complete = () => ({
      name: 'fire',
      routes: [{ path: '/fire', name: 'fire', component: () => null }],
      nav: [{ to: '/fire', labelKey: 'nav.fire' }],
      mapLayers: [{ id: 'fire-zones', zIndex: 20 }],
      panels: [{ id: 'fire-panel', component: () => null }],
      banners: [{ id: 'fire-alert', priority: 10, component: () => null }],
      liveHandlers: { fire_alert: () => {} },
      i18n: { en: { fire: 'Fire' }, bg: { fire: 'Пожар' } },
      depends: ['settings'],
    })
    expect(validateManifest(complete())).toEqual([])
    for (const field of ['name', 'routes', 'nav', 'mapLayers', 'panels', 'banners', 'liveHandlers', 'i18n', 'depends']) {
      const m = complete()
      delete m[field]
      const problems = validateManifest(m)
      expect(problems.length, `missing ${field}`).toBeGreaterThan(0)
      expect(problems.join('\n')).toContain(field)
    }
    const bad = complete()
    bad.i18n = { en: {} }
    expect(validateManifest(bad).join('\n')).toContain('i18n.bg')
    expect(validateManifest(null).length).toBeGreaterThan(0)
    expect(validateManifest(Object.assign(complete(), { name: 'Not A Name' })).join('\n')).toContain('name')
  })

  it('ratchet verdict: may shrink, never grow, skips when there is no base [T306]', () => {
    const base = JSON.stringify({ completed_step: 0, violations: ['a', 'b'] })
    expect(ratchetVerdict(null, ['a']).status).toBe('skip')
    expect(ratchetVerdict(base, ['a', 'b']).status).toBe('pass')
    expect(ratchetVerdict(base, ['a']).status).toBe('pass')
    expect(ratchetVerdict(base, ['a', 'b', 'c']).status).toBe('fail')
  })

  it('allowlist never grows against the merge base [T306]', (ctx) => {
    const sha = resolveMergeBase()
    if (!sha) {
      // Locally a missing base is a visible skip; in CI it must not fail open (checkout needs fetch-depth: 0).
      if (process.env.CI) throw new Error('no base ref resolves in CI: fetch the base branch or set ARCH_BASE_REF')
      ctx.skip('no base ref resolves (set ARCH_BASE_REF); shallow clone or no upstream/origin remote')
    }
    let baseText = null
    try {
      baseText = git(['show', `${sha}:./src/architecture.allowlist.json`])
    } catch {
      // absent at the base
    }
    const verdict = ratchetVerdict(baseText, readAllowlist().violations)
    if (verdict.status === 'skip') ctx.skip(verdict.reason)
    expect(verdict.status, verdict.reason).toBe('pass')
  })
})
