// Fire module manifest: plain data only, no OpenLayers (rule `manifest-reaches-no-openlayers`).
// The alarm banner is imported statically on purpose: the alarm must not wait for a chunk.
import { BANNER_PRIORITY } from '../../platform/map-shell/zorder.js'
import FireAlarmBanner from './components/FireAlarmBanner.vue'
import bg from './i18n/bg.js'
import en from './i18n/en.js'
import { FIRE_MAP_LAYERS } from './map/layers.js'

import { useFireStore } from './store.js'

export { useFireStore }

export default {
  name: 'fire',
  routes: [],
  nav: [],
  mapLayers: FIRE_MAP_LAYERS,
  panels: [],
  banners: [{ id: 'fire-alarm', priority: BANNER_PRIORITY.fireAlarm, component: FireAlarmBanner }],
  // Live socket contributions (read by platform/live/dispatch.js). The store is read inside each function so
  // the Pinia that is active at call time is the one used. A rejected promise is logged by dispatchLive.
  liveHandlers: {
    fire_data_updated: (msg) => useFireStore().applyFireDataUpdated(msg),
    fire_zones_updated: () => useFireStore().applyFireZonesUpdated(),
    fire_alert: (msg) => useFireStore().applyFireAlert(msg),
    fire_alert_repeat: (msg) => useFireStore().applyFireAlertRepeat(msg),
    fire_alert_updated: (msg) => useFireStore().applyFireAlertUpdated(msg),
  },
  live: {
    // A shown feed whose last fetch failed is retried on every tick (the layers themselves are not re-pulled:
    // the backend polls EFFIS every 30 min). Open alarms ARE re-pulled: a missed push must not hide one (BP-02).
    onTick: () => {
      const store = useFireStore()
      return Promise.allSettled([store.retryFailed(), store.fetchOpenAlerts()])
    },
    // Layers refetch on a reconnect, not on the 45 s tick.
    onReconnect: () => useFireStore().refreshVisible(),
  },
  i18n: { en, bg },
  depends: [],
}
