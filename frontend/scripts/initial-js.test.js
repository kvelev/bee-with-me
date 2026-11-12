import { describe, expect, it } from 'vitest'
import { initialJsFiles } from './initial-js.mjs'

describe('initial-js', () => {
  it('counts the entry and its preloads under any base [B146]', () => {
    for (const base of ['/', './', '/bee/', '']) {
      const html = `<script type="module" crossorigin src="${base}assets/index-a.js"></script>`
        + `<link rel="modulepreload" crossorigin href="${base}assets/vendor-b.js">`
        + `<link rel="stylesheet" href="${base}assets/index-c.css">`
      expect([...initialJsFiles(html)].sort(), base).toEqual(['assets/index-a.js', 'assets/vendor-b.js'])
    }
  })
})
