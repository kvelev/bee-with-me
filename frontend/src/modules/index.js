// The module list: one manifest per line, alphabetical. The router, the navigation and the map shell read this
// list and never name a module (Architecture/application/modular-monolith.md, section 3.2).
// Import a module only through its index.js (rule `modules-only-through-index`).
import devices from './devices/index.js'
import fire from './fire/index.js'
import people from './people/index.js'
import settings from './settings/index.js'
import sos from './sos/index.js'
import teams from './teams/index.js'
import tracking from './tracking/index.js'
import weather from './weather/index.js'

export const MODULES = [
  devices,
  fire,
  people,
  settings,
  sos,
  teams,
  tracking,
  weather,
]
