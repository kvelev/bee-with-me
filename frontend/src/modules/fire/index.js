// Fire module manifest: plain data only, no OpenLayers (rule `manifest-reaches-no-openlayers`).
// The alarm banner is imported statically on purpose: the alarm must not wait for a chunk.
import { BANNER_PRIORITY } from '../../platform/map-shell/zorder.js'
import FireAlarmBanner from './components/FireAlarmBanner.vue'
import FireDialogs from './components/FireDialogs.vue'
import FireMapPopup from './components/FireMapPopup.vue'
import FireMapPanel from './components/FireMapPanel.vue'
import FireZonesNote from './components/FireZonesNote.vue'
import bg from './i18n/bg.js'
import en from './i18n/en.js'
import { FIRE_MAP_LAYERS } from './map/layers.js'

import { useFireStore } from './store.js'
import { useFireUi } from './ui.js'

export { useFireStore }
export { useFireUi } from './ui.js'

export default {
  name: 'fire',
  routes: [],
  nav: [],
  mapLayers: FIRE_MAP_LAYERS,
  // The map panel (pill, attribution, focus ring, layer sync) is imported statically: it imports no ol module,
  // the focus overlay class comes from context.mapKit.
  // The zones-failed note sits in the toolbar row next to the layer buttons, so it is a toolbar panel of its own.
  panels: [
    { id: 'fire-map', host: 'map', order: 20, component: FireMapPanel },
    { id: 'fire-zones-note', host: 'map-toolbar', order: 10, component: FireZonesNote },
    // The field-report and zone dialogs (state in useFireUi); they open from the popup, the menu and the tracker row.
    { id: 'fire-dialogs', host: 'map', order: 30, component: FireDialogs },
  ],
  // The popup of a hotspot or burnt-area feature, and the map context-menu item that reports a fire at the pointer.
  popups: [{ id: 'fire', component: FireMapPopup, kinds: ['hotspot', 'burnt_area'] }],
  contextMenu: [{
    id: 'fire-report-here', order: 10, labelKey: 'fire.report.here', testId: 'report-fire-here',
    onSelect: ({ lonLat }) => useFireUi().openDialog({ kind: 'report', target: { latitude: lonLat[1], longitude: lonLat[0] } }),
  }],
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
