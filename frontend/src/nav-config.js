import { MODULES } from './modules/index.js'
import { collectNav } from './platform/registry.js'

// Edit the icon value for each nav item here.
// Any emoji or single character works — e.g. '🗺', '📍', '🧭'

const STATIC_NAV = [
  { to: '/map',     labelKey: 'nav.map',     icon: '🗺', order: 10 },
  { to: '/users',   labelKey: 'nav.users',   icon: '👤', order: 20 },
  { to: '/groups',  labelKey: 'nav.groups',  icon: '👥', order: 30 },
  { to: '/devices', labelKey: 'nav.devices', icon: '📡', order: 40 },
  { to: '/export',  labelKey: 'nav.export',  icon: '📤', order: 50 },
  { to: '/selectofflinemap', labelKey: 'nav.selectofflinemap', icon: '📦', order: 60 },
  { to: '/settings', labelKey: 'nav.settings', icon: '⚙', adminOnly: true, order: 70 },
  { to: '/about',   labelKey: 'nav.about',   icon: 'ℹ️', order: 80 },
]

// Static items plus the items of every module, sorted by `order`.
export const NAV_ITEMS = collectNav(STATIC_NAV, MODULES)
