// The panels the modules contribute to the Settings page (host `settings`), in order.
// The Settings view lives in a module that the module list loads lazily, so it may neither import the list
// (rule `modules-only-through-index`) nor reach it through a helper (rule `no-circular`). The manifests are
// therefore found with a glob, as src/i18n does for the module texts. A test pins this list to
// collectPanels(MODULES, 'settings').
import { collectPanels } from '../platform/map-shell/contributions.js'

const manifests = Object.values(import.meta.glob('../modules/*/index.js', { eager: true, import: 'default' }))

export const settingsPanels = collectPanels(manifests, 'settings')
