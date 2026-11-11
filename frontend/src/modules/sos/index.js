// SOS module manifest: plain data only, no OpenLayers (rule `manifest-reaches-no-openlayers`).
// The banner is imported statically on purpose: an alarm must not wait for a chunk.
import { BANNER_PRIORITY } from '../../platform/map-shell/zorder.js'
import SOSBanner from './components/SOSBanner.vue'
import bg from './i18n/bg.js'
import en from './i18n/en.js'
import { useSosStore } from './store.js'

export { useSosStore }

export default {
  name: 'sos',
  routes: [],
  nav: [],
  mapLayers: [],
  panels: [],
  banners: [{ id: 'sos', priority: BANNER_PRIORITY.sos, component: SOSBanner }],
  liveHandlers: {
    sos_alert: (msg) => useSosStore().applySOSAlert(msg),
  },
  live: {
    // Creating the store registers its hook on the tracking store, so it must exist before the first message.
    setup: () => { useSosStore() },
    onTick: () => useSosStore().fetchSOS(),
  },
  i18n: { en, bg },
  depends: ['tracking'],
}
