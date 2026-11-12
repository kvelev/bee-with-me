// SOS module manifest: plain data only, no OpenLayers (rule `manifest-reaches-no-openlayers`).
// The banner is imported statically on purpose: an alarm must not wait for a chunk.
import { BANNER_PRIORITY } from '../../platform/map-shell/zorder.js'
import SOSBanner from './components/SOSBanner.vue'
import SOSToast from './components/SOSToast.vue'
import bg from './i18n/bg.js'
import en from './i18n/en.js'
import { useSosStore } from './store.js'

export { useSosStore }

export default {
  name: 'sos',
  routes: [],
  nav: [],
  mapLayers: [],
  // The toast sits at the map root. retryKey: a toast that failed to render is tried again with the next notification,
  // so one render error cannot hide every later SOS toast (the banner does not depend on it).
  panels: [
    { id: 'sos-toast', host: 'map-root', order: 10, component: SOSToast, retryKey: () => useSosStore().sosNotifications.length },
  ],
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
