// The tracking map layers as declarations: plain data, no OpenLayers (the manifest imports this file; the
// layers themselves live in ./index.js). The trail and checkpoint layers start hidden and are switched
// together by the trail button; the tracker layer is always on.
import { Z } from '../../../platform/map-shell/zorder.js'

export const TRACKING_TRAIL_LAYER = { id: 'tracking-trail', zIndex: Z.trail }
export const TRACKING_CHECKPOINTS_LAYER = { id: 'tracking-checkpoints', zIndex: Z.checkpoints }
export const TRACKING_TRACKERS_LAYER = { id: 'tracking-trackers', zIndex: Z.trackers }

export const TRACKING_MAP_LAYERS = [TRACKING_TRAIL_LAYER, TRACKING_CHECKPOINTS_LAYER, TRACKING_TRACKERS_LAYER]
