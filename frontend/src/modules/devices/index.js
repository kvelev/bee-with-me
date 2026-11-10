// Devices module manifest: plain data only, no OpenLayers (rule `manifest-reaches-no-openlayers`).
import bg from './i18n/bg.js'
import en from './i18n/en.js'

export default {
  name: 'devices',
  // The page still lives in src/views/ until its own move task; the path changes then.
  routes: [
    { path: '/devices', name: 'devices', component: () => import('../../views/DevicesView.vue') },
  ],
  nav: [{ to: '/devices', labelKey: 'nav.devices', icon: '📡', order: 40 }],
  mapLayers: [],
  panels: [],
  banners: [],
  liveHandlers: {},
  i18n: { en, bg },
  depends: ['people'],
}
