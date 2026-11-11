// Live work that has not moved into a module yet: what the socket does with each message type, on every
// resync tick and on a reconnect. Each entry leaves this file when its module takes it over and the file
// goes when it is empty (tracking plan T544, fire plan T510). Stores are reached lazily so the Pinia that
// is active at call time is the one used.
import { useLocationsStore } from '../stores/locations'
import { useFireStore } from '../stores/fire'

export const LEGACY_LIVE = {
  handlers: [
    { type: 'location_update',     handler: (msg) => useLocationsStore().applyLocationUpdate(msg) },            // until step 2
    { type: 'sos_alert',           handler: (msg) => useLocationsStore().applySOSAlert(msg) },                  // until step 2
    { type: 'serial_status',       handler: (msg) => useLocationsStore().applySerialStatus(msg) },              // until step 2
    { type: 'fire_data_updated',   handler: (msg) => { useFireStore().applyFireDataUpdated(msg).catch(() => {}) } },     // until step 3
    { type: 'fire_zones_updated',  handler: () => { useFireStore().applyFireZonesUpdated().catch(() => {}) } },          // until step 3
    { type: 'fire_alert',          handler: (msg) => useFireStore().applyFireAlert(msg) },                      // until step 3
    { type: 'fire_alert_repeat',   handler: (msg) => { useFireStore().applyFireAlertRepeat(msg).catch(() => {}) } },     // until step 3
    { type: 'fire_alert_updated',  handler: (msg) => useFireStore().applyFireAlertUpdated(msg) },               // until step 3
  ],
  hooks: {
    onTick: [
      // until step 2: one entry, as before (a failure of one fetch ends the batch, the next tick tries again)
      () => {
        const store = useLocationsStore()
        return Promise.all([store.fetchLive(), store.fetchSOS(), store.fetchTrail()])
      },
      // until step 3: a shown feed whose last fetch failed is retried on every tick. The backend polls EFFIS
      // every 30 min, so the layers themselves are not re-pulled here. Not awaited, as before.
      () => { useFireStore().retryFailed().catch(() => { /* fetchFailed drives the pill */ }) },
      // until step 3: open fire alarms ARE re-pulled on every tick: a missed push must not hide an alarm (BP-02).
      () => { useFireStore().fetchOpenAlerts().catch(() => { /* alertsFailed drives the banner notice */ }) },
    ],
    onReconnect: [
      // until step 3: fire layers refetch on a reconnect, on `fire_data_updated` and on layer toggle, but not on
      // the 45 s tick (it would re-pull every hotspot and burnt-area polygon 40 times per EFFIS poll).
      () => { useFireStore().refreshVisible().catch(() => { /* fetchFailed drives the pill */ }) },
    ],
  },
}
