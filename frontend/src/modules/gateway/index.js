// Gateway module manifest: plain data only, no OpenLayers (rule `manifest-reaches-no-openlayers`).
// The pill is imported statically: a few lines, no ol module. It sits in the `map` host, inside `.map-layout`, because
// it is positioned absolutely against the map area (the `map-root` host is outside it, in the page).
import GatewayStatus from './components/GatewayStatus.vue'
import bg from './i18n/bg.js'
import en from './i18n/en.js'
import { useGatewayStore } from './store.js'

export { useGatewayStore }

export default {
  name: 'gateway',
  routes: [],
  nav: [],
  mapLayers: [],
  panels: [
    { id: 'gateway-status', host: 'map', order: 20, component: GatewayStatus },
  ],
  banners: [],
  liveHandlers: {
    serial_status: (msg) => useGatewayStore().applyStatus(msg),
  },
  live: {
    // Once when the live channel first connects on the page, and again with every resync tick (which also runs
    // after a reconnect): a status that was missed, or fetched before a login, arrives with the next tick.
    setup: () => useGatewayStore().fetchStatus(),
    onTick: () => useGatewayStore().fetchStatus(),
  },
  i18n: { en, bg },
  depends: [],
}
