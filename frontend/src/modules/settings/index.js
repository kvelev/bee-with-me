// Settings module manifest: plain data only, no OpenLayers (rule `manifest-reaches-no-openlayers`).
import bg from './i18n/bg.js'
import en from './i18n/en.js'
import { HQ_LAYER } from './map/layers.js'

export default {
  name: 'settings',
  routes: [
    { path: '/settings', name: 'settings', component: () => import('./views/SettingsView.vue'), meta: { adminOnly: true } },
  ],
  // order 70: the place the static item had between "select offline map" (60) and "about" (80)
  nav: [{ to: '/settings', labelKey: 'nav.settings', icon: '⚙', adminOnly: true, order: 70 }],
  mapLayers: [HQ_LAYER],
  panels: [],
  banners: [],
  liveHandlers: {},
  i18n: { en, bg },
  depends: [],
}
