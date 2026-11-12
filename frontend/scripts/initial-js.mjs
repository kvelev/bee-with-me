// Initial JavaScript: the sum of the .js files that dist/index.html names (the entry and its modulepreload links).
// Run in frontend/ after `npm run build`: node scripts/initial-js.mjs
import { existsSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

/** The `assets/*.js` paths that the HTML loads, whatever the base: `/`, `./`, `/bee/` or none (B146). */
export function initialJsFiles(html) {
  const files = new Set()
  for (const match of html.matchAll(/(?:src|href)="[^"]*?(assets\/[^"]+\.js)"/g)) files.add(match[1])
  return files
}

function main() {
  const dist = 'dist'
  const indexPath = join(dist, 'index.html')
  if (!existsSync(indexPath)) {
    console.error('dist/index.html is missing: run `npm run build` first')
    process.exit(1)
  }
  const files = initialJsFiles(readFileSync(indexPath, 'utf8'))
  let bytes = 0
  for (const file of files) bytes += statSync(join(dist, file)).size
  console.log(`${files.size} files, ${(bytes / 1000).toFixed(2)} kB`)
}

// Run only as a script, not when a test imports the function.
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main()
