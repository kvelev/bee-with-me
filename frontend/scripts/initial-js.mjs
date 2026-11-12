// Initial JavaScript: the sum of the .js files that dist/index.html names (the entry and its modulepreload links).
// Run in frontend/ after `npm run build`: node scripts/initial-js.mjs
import { existsSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

const dist = 'dist'
const indexPath = join(dist, 'index.html')
if (!existsSync(indexPath)) {
  console.error('dist/index.html is missing: run `npm run build` first')
  process.exit(1)
}
const html = readFileSync(indexPath, 'utf8')
const files = new Set()
for (const match of html.matchAll(/(?:src|href)="\/?(assets\/[^"]+\.js)"/g)) files.add(match[1])
let bytes = 0
for (const file of files) bytes += statSync(join(dist, file)).size
console.log(`${files.size} files, ${(bytes / 1000).toFixed(2)} kB`)
