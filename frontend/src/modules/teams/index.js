// Teams module manifest: plain data only, no OpenLayers (rule `manifest-reaches-no-openlayers`).
import bg from './i18n/bg.js'
import en from './i18n/en.js'

export default {
  name: 'teams',
  // The page still lives in src/views/ until its own move task; the path changes then.
  routes: [
    { path: '/groups', name: 'groups', component: () => import('../../views/GroupsView.vue') },
  ],
  nav: [{ to: '/groups', labelKey: 'nav.groups', icon: '👥', order: 30 }],
  mapLayers: [],
  panels: [],
  banners: [],
  liveHandlers: {},
  i18n: { en, bg },
  depends: ['people'],
}
