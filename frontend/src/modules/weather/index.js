// Weather module manifest: plain data only, no OpenLayers (rule `manifest-reaches-no-openlayers`).
// The buttons and the panel (info, legend, wind animation) are imported statically: they import no ol module,
// the map helpers come from context.mapKit and the tile layer from context.facade.
import WeatherPanel from './components/WeatherPanel.vue'
import WeatherToolbar from './components/WeatherToolbar.vue'
import bg from './i18n/bg.js'
import en from './i18n/en.js'

export default {
  name: 'weather',
  routes: [],
  nav: [],
  mapLayers: [],
  // The buttons sort before fire's zones note (order 10) so the toolbar reads: weather buttons, then the note.
  panels: [
    { id: 'weather-toolbar', host: 'map-toolbar', order: 5, component: WeatherToolbar },
    { id: 'weather-panel', host: 'map', order: 10, component: WeatherPanel },
  ],
  banners: [],
  liveHandlers: {},
  i18n: { en, bg },
  depends: [],
}
