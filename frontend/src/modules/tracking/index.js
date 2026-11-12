// Tracking module manifest: plain data only, no OpenLayers (rule `manifest-reaches-no-openlayers`).
// Part 1 carries the store, the libraries and the live handlers; the tracker panel and layers stay in the map view
// and `useMap` until T548 and T549.
import bg from './i18n/bg.js'
import en from './i18n/en.js'
import { useTrackingStore } from './store.js'

export { useTrackingStore }

export default {
  name: 'tracking',
  routes: [],
  nav: [],
  mapLayers: [],
  panels: [],
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
