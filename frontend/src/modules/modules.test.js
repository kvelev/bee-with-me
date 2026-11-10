// @vitest-environment node
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { cruise } from 'dependency-cruiser'
import extractDepcruiseConfig from 'dependency-cruiser/config-utl/extract-depcruise-config'
import { describe, expect, it } from 'vitest'
import bgFull, { core as bgCore } from '../i18n/bg.js'
import enFull, { core as enCore } from '../i18n/en.js'
import snapshot from '../i18n/keys.snapshot.json'
import { NAV_ITEMS } from '../nav-config.js'
import { checkModules, leafKeys, messageCollisions } from '../platform/registry.js'
import { MODULES } from './index.js'

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const FRONTEND = path.resolve(SRC, '..')
const CONFIG = path.join(FRONTEND, '.dependency-cruiser.cjs')
const SLOW = 120_000

// Static `import ... from 'x'`, `export ... from 'x'` and `import 'x'`; a lazy `import('x')` is not matched.
// A statement may follow another on the same line (`;` or `}` before it); comments are cut first, so a quote
// inside a comment between the braces cannot end the statement early (B92).
const STATIC_IMPORT = /(?:^|[\s;}])(?:import|export)\s*(?:[^'"();]*?\bfrom\s*)?['"]([^'"]+)['"]/g
const withoutComments = (text) => text.replace(/\/\*[\s\S]*?\*\//g, ' ').replace(/(^|\s)\/\/.*$/gm, '$1')
const isOpenLayers = (spec) => spec === 'ol' || spec.startsWith('ol/')

function resolveRelative(from, spec) {
  const base = path.resolve(path.dirname(from), spec)
  return [base, `${base}.js`, `${base}.vue`, path.join(base, 'index.js')].find((c) => fs.existsSync(c) && fs.statSync(c).isFile())
}

// The chain of file names from `entry` to an OpenLayers import through static imports only, or null.
function staticOlChain(entry) {
  const parent = new Map([[entry, null]])
  const queue = [entry]
  while (queue.length) {
    const file = queue.shift()
    const text = withoutComments(fs.readFileSync(file, 'utf8'))
    for (const [, spec] of text.matchAll(STATIC_IMPORT)) {
      if (isOpenLayers(spec)) {
        const chain = [spec]
        for (let f = file; f !== null; f = parent.get(f)) chain.unshift(path.basename(f))
        return chain
      }
      if (!spec.startsWith('.')) continue
      const next = resolveRelative(file, spec)
      if (next && !parent.has(next)) {
        parent.set(next, file)
        queue.push(next)
      }
    }
  }
  return null
}

// Every module's own dictionary files, by language (same glob the i18n index uses).
const dictionaries = (lang) => Object.entries(import.meta.glob('./*/i18n/*.js', { eager: true, import: 'default' }))
  .filter(([file]) => file.endsWith(`/${lang}.js`))

async function cruiseTree(baseDir) {
  const config = await extractDepcruiseConfig(CONFIG)
  const result = await cruise(['src'], { ...config.options, ruleSet: config, validate: true, baseDir })
  return result.output
}

function violationKeys(output) {
  return output.summary.violations
    .filter((v) => v.rule.severity === 'error')
    .map((v) => `${v.rule.name}|${v.from}|${v.to}`.replaceAll('\\', '/'))
    .sort()
}

async function cruiseFixture(files) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'modules-fixture-'))
  try {
    for (const [rel, body] of Object.entries(files)) {
      const file = path.join(root, rel)
      fs.mkdirSync(path.dirname(file), { recursive: true })
      fs.writeFileSync(file, body)
    }
    return violationKeys(await cruiseTree(root))
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
}

describe('frontend modules', () => {
  it('the real module list is valid [T403]', () => {
    expect(checkModules(MODULES)).toEqual([])
    console.info(`i18n leaves en=${leafKeys(enFull).length} bg=${leafKeys(bgFull).length}`)
  })

  it('every folder under src/modules with an index.js is in the list and the reverse [T403]', () => {
    const dir = path.join(SRC, 'modules')
    const folders = fs.readdirSync(dir, { withFileTypes: true })
      .filter((e) => e.isDirectory() && fs.existsSync(path.join(dir, e.name, 'index.js')))
      .map((e) => e.name)
      .sort()
    expect(MODULES.map((m) => m.name).sort()).toEqual(folders)
  })

  it('each module i18n is its own files and en and bg have the same keys [T403]', () => {
    for (const m of MODULES) {
      expect(leafKeys(m.i18n.en), m.name).toEqual(leafKeys(m.i18n.bg))
      for (const lang of ['en', 'bg']) {
        const entry = dictionaries(lang).find(([f]) => f === `./${m.name}/i18n/${lang}.js`)
        expect(entry, `${m.name} ${lang}`).toBeDefined()
        expect(m.i18n[lang]).toBe(entry[1])
      }
    }
  })

  it('no key is defined twice [T403]', () => {
    expect(messageCollisions(enCore, dictionaries('en').map(([, d]) => d))).toEqual([])
    expect(messageCollisions(bgCore, dictionaries('bg').map(([, d]) => d))).toEqual([])
  })

  it('no text key was lost [T403]', () => {
    const en = new Set(leafKeys(enFull))
    const bg = new Set(leafKeys(bgFull))
    expect(snapshot.filter((k) => !en.has(k))).toEqual([])
    expect(snapshot.filter((k) => !bg.has(k))).toEqual([])
  })

  it('the merged dictionaries are the core plus the module files [T403]', () => {
    const union = (core, dicts) => [...new Set([...leafKeys(core), ...dicts.flatMap((d) => leafKeys(d))])].sort()
    expect(leafKeys(enFull)).toEqual(union(enCore, dictionaries('en').map(([, d]) => d)))
    expect(leafKeys(bgFull)).toEqual(union(bgCore, dictionaries('bg').map(([, d]) => d)))
  })

  it('navigation order is unchanged [T403]', () => {
    expect(NAV_ITEMS.map((i) => i.to)).toEqual(
      ['/map', '/users', '/groups', '/devices', '/export', '/selectofflinemap', '/settings', '/about'],
    )
  })

  it('a file that re-exports from src/modules is only a re-export [T403]', () => {
    const offenders = []
    for (const sub of ['stores', 'composables', 'lib']) {
      const dir = path.join(SRC, sub)
      for (const name of fs.readdirSync(dir)) {
        if (!name.endsWith('.js') || name.endsWith('.test.js')) continue
        const text = fs.readFileSync(path.join(dir, name), 'utf8')
        if (!text.includes("export * from '../modules/")) continue
        const code = text.split(/\r?\n/).filter((l) => l.trim() !== '' && !l.trim().startsWith('//'))
        if (!code.every((l) => /^export \* from '\.\.\/modules\/[^']+'\s*$/.test(l))) offenders.push(`${sub}/${name}`)
      }
    }
    expect(offenders).toEqual([])
  })

  it('module lib is pure [T403]', async () => {
    const keys = await cruiseFixture({
      'src/modules/m/store.js': 'export default 1\n',
      'src/modules/m/lib/a.js': "import s from '../store.js'\nexport default s\n",
    })
    expect(keys).toContain('lib-is-pure|src/modules/m/lib/a.js|src/modules/m/store.js')
  }, SLOW)

  it('a manifest that reaches OpenLayers through a static import is a violation and a lazy view is not [T403]', () => {
    // dependency-cruiser cannot filter a reachability rule by dependency type, so the walk is done here.
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'modules-ol-'))
    try {
      const write = (rel, body) => {
        const file = path.join(root, rel)
        fs.mkdirSync(path.dirname(file), { recursive: true })
        fs.writeFileSync(file, body)
      }
      write('m/index.js', "import l from './layers.js'\nexport default l\n")
      write('m/layers.js', "import V from 'ol/layer/Vector'\nexport default V\n")
      write('n/index.js', "export default { component: () => import('./views/V.js') }\n")
      write('n/views/V.js', "import V from 'ol/layer/Vector'\nexport default V\n")
      write('p/index.js', "export * from './deep/a.js'\n")
      write('p/deep/a.js', "import './b'\n")
      write('p/deep/b.js', "import 'ol'\n")
      expect(staticOlChain(path.join(root, 'm/index.js'))).toEqual(['index.js', 'layers.js', 'ol/layer/Vector'])
      expect(staticOlChain(path.join(root, 'n/index.js'))).toBeNull()
      expect(staticOlChain(path.join(root, 'p/index.js'))).not.toBeNull()
      write('q/index.js', "import {\n  Vector,\n  Tile\n} from 'ol/layer'\nexport default Vector\n")
      write('r/index.js', "export {\n  a\n} from 'ol/source'\n")
      write('s/index.js', "import './side.js'\nexport default 1\n")
      write('s/side.js', 'export const x = 1\n')
      expect(staticOlChain(path.join(root, 'q/index.js'))).toEqual(['index.js', 'ol/layer'])
      expect(staticOlChain(path.join(root, 'r/index.js'))).toEqual(['index.js', 'ol/source'])
      expect(staticOlChain(path.join(root, 's/index.js'))).toBeNull()
    } finally {
      fs.rmSync(root, { recursive: true, force: true })
    }
  })

  it('staticOlChain sees two imports on one line and ignores a quote in a comment inside the braces [B92]', () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'modules-ol-b92-'))
    try {
      const write = (rel, body) => {
        const file = path.join(root, rel)
        fs.mkdirSync(path.dirname(file), { recursive: true })
        fs.writeFileSync(file, body)
      }
      write('a/index.js', "import './side.js'; import V from 'ol/layer/Vector'\nexport default V\n")
      write('a/side.js', 'export const x = 1\n')
      write('b/index.js', "import {\n  one, // it's the first\n  two\n} from 'ol/layer'\nexport default one\n")
      write('c/index.js', "import {\n  one, /* don't */\n  two\n} from './x.js'\nexport default one\n")
      write('c/x.js', 'export const one = 1\nexport const two = 2\n')
      write('d/index.js', "// import V from 'ol'\nexport default () => import('ol')\n")
      expect(staticOlChain(path.join(root, 'a/index.js'))).toEqual(['index.js', 'ol/layer/Vector'])
      expect(staticOlChain(path.join(root, 'b/index.js'))).toEqual(['index.js', 'ol/layer'])
      expect(staticOlChain(path.join(root, 'c/index.js'))).toBeNull()
      expect(staticOlChain(path.join(root, 'd/index.js'))).toBeNull()
    } finally {
      fs.rmSync(root, { recursive: true, force: true })
    }
  })

  it('no manifest imports OpenLayers, directly or through static imports [T403]', () => {
    const dir = path.join(SRC, 'modules')
    const reached = fs.readdirSync(dir, { withFileTypes: true })
      .filter((e) => e.isDirectory() && fs.existsSync(path.join(dir, e.name, 'index.js')))
      .map((e) => [e.name, staticOlChain(path.join(dir, e.name, 'index.js'))])
      .filter(([, chain]) => chain !== null)
    expect(reached).toEqual([])
  })
})
