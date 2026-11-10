// People module manifest: plain data only, no OpenLayers (rule `manifest-reaches-no-openlayers`).
import bg from './i18n/bg.js'
import en from './i18n/en.js'

export default {
  name: 'people',
  routes: [
    { path: '/users', name: 'users', component: () => import('./views/UsersView.vue') },
  ],
  nav: [{ to: '/users', labelKey: 'nav.users', icon: '👤', order: 20 }],
  mapLayers: [],
  panels: [],
  banners: [],
  liveHandlers: {},
  i18n: { en, bg },
  depends: [],
}
