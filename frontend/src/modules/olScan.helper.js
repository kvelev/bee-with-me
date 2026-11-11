// Test helper (imported by tests only, never by app code): finds a static path from a file to OpenLayers.
// It reads the disk with `fs`, so it must stay out of the app graph: no source file imports it, so the Vite build
// does not reach it, and it has no import that a dependency-cruiser rule forbids.
import fs from 'node:fs'
import path from 'node:path'

// Static `import ... from 'x'`, `export ... from 'x'` and `import 'x'`; a lazy `import('x')` is not matched.
// A statement may follow another on the same line (`;` or `}` before it); comments are cut first, so a quote
// inside a comment between the braces cannot end the statement early (B92).
const STATIC_IMPORT = /(?:^|[\s;}])(?:import|export)\s*(?:[^'"();]*?\bfrom\s*)?['"]([^'"]+)['"]/g
const withoutComments = (text) => text.replace(/\/\*[\s\S]*?\*\//g, ' ').replace(/(^|\s)\/\/.*$/gm, '$1')
const isOpenLayers = (spec) => spec === 'ol' || spec.startsWith('ol/')

// A single-file component imports from its <script> blocks only; the template may hold any text.
function codeOf(file) {
  const text = fs.readFileSync(file, 'utf8')
  if (!file.endsWith('.vue')) return withoutComments(text)
  const scripts = [...text.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)].map((m) => m[1])
  return withoutComments(scripts.join('\n'))
}

function resolveRelative(from, spec) {
  const base = path.resolve(path.dirname(from), spec)
  return [base, `${base}.js`, `${base}.vue`, path.join(base, 'index.js')].find((c) => fs.existsSync(c) && fs.statSync(c).isFile())
}

// The chain of file names from `entry` to an OpenLayers import through static imports only, or null.
export function staticOlChain(entry) {
  const parent = new Map([[entry, null]])
  const queue = [entry]
  while (queue.length) {
    const file = queue.shift()
    for (const [, spec] of codeOf(file).matchAll(STATIC_IMPORT)) {
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
