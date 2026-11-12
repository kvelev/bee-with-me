// One map entry per module that draws on the map, alphabetical. Only useMap.js imports this file.
// A map entry (src/modules/<name>/map/index.js) may import ol/*; a manifest (index.js) never does.
import fireMap from './fire/map/index.js'
import settingsMap from './settings/map/index.js'
import trackingMap from './tracking/map/index.js'

export const MAP_MODULES = [fireMap, settingsMap, trackingMap]
