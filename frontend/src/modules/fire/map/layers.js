// The fire map layers as declarations: plain data, no OpenLayers (a manifest may import this, the
// layers themselves live in index.js). Order in the array is the order the layers are added to
// the map; the toggle `order` is the order of the buttons (burnt, hotspots, zones).
import { Z } from '../../../platform/map-shell/zorder'
import { useFireStore } from '../store.js'
import { useFireUi } from '../ui.js'

// The state pair of a layer button: the flag lives in the fire store, a click goes through the fire UI store.
const layerToggle = (key) => ({
  key,
  isOn: () => !!useFireStore().layers[key],
  set: (on) => useFireUi().setLayer(key, on),
})

export const FIRE_MAP_LAYERS = [
  { id: 'fire-burnt',    zIndex: Z.burnt,    toggle: { labelKey: 'fire.layers.burnt',    order: 10, ...layerToggle('burnt') } },
  { id: 'fire-zones',    zIndex: Z.zones,    toggle: { labelKey: 'fire.layers.zones',    order: 30, adminOnly: true, ...layerToggle('zones') } },
  { id: 'fire-hotspots', zIndex: Z.hotspots, toggle: { labelKey: 'fire.layers.hotspots', order: 20, ...layerToggle('hotspots') } },
]
