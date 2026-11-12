// Tracking module manifest: plain data only, no OpenLayers (rule `manifest-reaches-no-openlayers`).
// Carries the store, the libraries, the live handlers and the tracker panel; the tracker layers stay in `useMap`
// until T632. The panel is imported statically: it imports no ol module, the map reaches it through `context`.
import TrackerPanel from './components/TrackerPanel.vue'
import bg from './i18n/bg.js'
import en from './i18n/en.js'
import { useTrackingStore } from './store.js'
import { useTrackerUi } from './ui.js'

export { useTrackingStore, useTrackerUi }

export default {
  name: 'tracking',
  routes: [],
  nav: [],
  mapLayers: [],
  // The tracker list sits in the `map` host (inside .map-layout, next to the map), ahead of the pills (order 20).
  panels: [
    { id: 'tracker-panel', host: 'map', order: 10, component: TrackerPanel },
  ],
  banners: [],
  liveHandlers: {
    location_update: (msg) => useTrackingStore().applyLocationUpdate(msg),
  },
  live: {
    // One entry: a failure of one fetch ends the batch, the next tick tries again.
    onTick: () => {
      const store = useTrackingStore()
      return Promise.all([store.fetchLive(), store.fetchTrail()])
    },
  },
  i18n: { en, bg },
  depends: [],
}
