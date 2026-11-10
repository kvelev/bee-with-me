// The fire map layers as declarations: plain data, no OpenLayers (a manifest may import this, the
// layers themselves live in fireLayers.js). Order in the array is the order the layers are added to
// the map; the toggle `order` is the order of the buttons (burnt, hotspots, zones).
// until step 2
import { Z } from '../../platform/map-shell/zorder'

export const FIRE_MAP_LAYERS = [
  { id: 'fire-burnt',    zIndex: Z.burnt,    toggle: { labelKey: 'fire.layers.burnt',    order: 10 } },
  { id: 'fire-zones',    zIndex: Z.zones,    toggle: { labelKey: 'fire.layers.zones',    order: 30, adminOnly: true } },
  { id: 'fire-hotspots', zIndex: Z.hotspots, toggle: { labelKey: 'fire.layers.hotspots', order: 20 } },
]
