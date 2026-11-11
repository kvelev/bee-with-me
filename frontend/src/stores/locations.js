import { defineStore, storeToRefs } from 'pinia'
import { useSosStore } from '../modules/sos/index.js'
import { useTrackingStore } from '../modules/tracking/index.js'

/** The old single store as a facade over `tracking` (positions, trails, connection) and `sos` (alerts, toasts).
 *  Same 23 names as before; each is the ref or action of the store that owns it, so an assignment through
 *  the facade reaches the owner. New code reads the two stores directly. */
export const useLocationsStore = defineStore('locations', () => {
  const tracking = useTrackingStore()
  const sos = useSosStore()
  const {
    positions, trails, serialStatus, positionList, wsConnected, lastSyncAt, fromSnapshot, silentList, lostList,
  } = storeToRefs(tracking)
  const { sosAlerts, sosNotifications, hasSOS } = storeToRefs(sos)

  function removePosition(deviceId) {
    tracking.removePosition(deviceId)
    sos.forgetDevice(deviceId)
  }

  return {
    positions, sosAlerts, sosNotifications, trails, serialStatus, positionList, hasSOS,
    wsConnected, lastSyncAt, fromSnapshot, silentList, lostList,
    fetchLive: tracking.fetchLive, fetchSOS: sos.fetchSOS, fetchTrail: tracking.fetchTrail,
    setConnected: tracking.setConnected,
    applyLocationUpdate: tracking.applyLocationUpdate, applySOSAlert: sos.applySOSAlert,
    applySerialStatus: tracking.applySerialStatus, resolveSOS: sos.resolveSOS,
    dismissSOSNotification: sos.dismissSOSNotification,
    removePosition, resetTrail: tracking.resetTrail,
  }
})
