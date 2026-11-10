// The settings module's map layer declarations: plain data, no OpenLayers (the manifest imports this
// file; the layer itself lives in ./index.js). The HQ marker sits above the repeaters and below the
// trackers' measure layer, where it has always been.
import { Z } from '../../../platform/map-shell/zorder.js'

export const HQ_LAYER = { id: 'settings-hq', zIndex: Z.hq }
