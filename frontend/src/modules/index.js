// The module list: one manifest per line, alphabetical. The router, the navigation and the map shell read this
// list and never name a module (Architecture/application/modular-monolith.md, section 3.2).
// Import a module only through its index.js (rule `modules-only-through-index`).
import settings from './settings/index.js'

export const MODULES = [
  settings,
]
