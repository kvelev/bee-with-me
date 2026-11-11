// Live work that has not moved into a module yet: what the socket does with each message type, on every
// resync tick and on a reconnect. Each entry leaves this file when its module takes it over and the file
// goes when it is empty (tracking plan T544; the fire entries left in fire plan T510). Stores are reached lazily so the Pinia that
// is active at call time is the one used.
import { useLocationsStore } from '../stores/locations'

export const LEGACY_LIVE = {
  handlers: [
    { type: 'location_update',     handler: (msg) => useLocationsStore().applyLocationUpdate(msg) },            // until step 2
    { type: 'sos_alert',           handler: (msg) => useLocationsStore().applySOSAlert(msg) },                  // until step 2
    { type: 'serial_status',       handler: (msg) => useLocationsStore().applySerialStatus(msg) },              // until step 2
  ],
  hooks: {
    onTick: [
      // until step 2: one entry, as before (a failure of one fetch ends the batch, the next tick tries again)
      () => {
        const store = useLocationsStore()
        return Promise.all([store.fetchLive(), store.fetchSOS(), store.fetchTrail()])
      },
    ],
    onReconnect: [],
  },
}
