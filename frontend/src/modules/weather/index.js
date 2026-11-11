// Weather module manifest: plain data only, no OpenLayers (rule `manifest-reaches-no-openlayers`).
// Part 1 carries the libraries and the texts; the buttons, panel and wind animation follow in T522.
import bg from './i18n/bg.js'
import en from './i18n/en.js'

export default {
  name: 'weather',
  routes: [],
  nav: [],
  mapLayers: [],
  panels: [],
  banners: [],
  liveHandlers: {},
  i18n: { en, bg },
  depends: [],
}
