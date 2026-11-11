// Fire module manifest: plain data only, no OpenLayers (rule `manifest-reaches-no-openlayers`).
// The alarm banner is imported statically on purpose: the alarm must not wait for a chunk.
import { BANNER_PRIORITY } from '../../platform/map-shell/zorder.js'
import FireAlarmBanner from './components/FireAlarmBanner.vue'
import bg from './i18n/bg.js'
import en from './i18n/en.js'
import { FIRE_MAP_LAYERS } from './map/layers.js'

export { useFireStore } from './store.js'

export default {
  name: 'fire',
  routes: [],
  nav: [],
  mapLayers: FIRE_MAP_LAYERS,
  panels: [],
  banners: [{ id: 'fire-alarm', priority: BANNER_PRIORITY.fireAlarm, component: FireAlarmBanner }],
  liveHandlers: {},
  i18n: { en, bg },
  depends: [],
}
