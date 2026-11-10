// Banners of features that have no module yet, in the shape of a manifest `banners` item.
// They leave this list when their module takes them over.
import SOSBanner from './SOSBanner.vue'
import FireAlarmBanner from './FireAlarmBanner.vue'
import { BANNER_PRIORITY } from '../platform/map-shell/zorder.js'

export const LEGACY_BANNERS = [
  { id: 'sos', priority: BANNER_PRIORITY.sos, component: SOSBanner }, // until step 3
  { id: 'fire-alarm', priority: BANNER_PRIORITY.fireAlarm, component: FireAlarmBanner }, // until step 2
]
