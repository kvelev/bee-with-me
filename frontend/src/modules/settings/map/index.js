// The settings module's map entry: the HQ marker and HQ placement. It is a map contribution in the shape
// of createMapShell's `install` (layers by declared id, then `setup`). It may import ol/*; the manifest
// (../index.js) never does.
import VectorLayer from 'ol/layer/Vector'
import VectorSource from 'ol/source/Vector'
import Feature from 'ol/Feature'
import Point from 'ol/geom/Point'
import { fromLonLat, toLonLat } from 'ol/proj'
import { Fill, Stroke, Style, Text } from 'ol/style'
import RegularShape from 'ol/style/RegularShape'
import { HQ_LAYER } from './layers.js'

const DEFAULT_LABEL = 'ЩАБ'
const HQ_MODE = 'hq-place'

function makeHQStyle(label) {
  return new Style({
    image: new RegularShape({
      points:  4,
      radius:  15,
      radius2: 4,
      angle:   0,
      fill:    new Fill({ color: '#fbbf24' }),
      stroke:  new Stroke({ color: '#000', width: 2 }),
    }),
    text: new Text({
      text:    label || DEFAULT_LABEL,
      offsetY: -22,
      font:    'bold 13px system-ui',
      fill:    new Fill({ color: '#fbbf24' }),
      stroke:  new Stroke({ color: '#000', width: 3 }),
    }),
  })
}

function createHQLayer() {
  return new VectorLayer({ source: new VectorSource() })
}

function setupHQMap(shell, ctx) {
  const layer = shell.layer(HQ_LAYER.id)
  if (!layer) throw new Error('the HQ layer is not registered')
  const source = layer.getSource()
  let label = DEFAULT_LABEL

  function setHQ(loc, newLabel) {
    label = newLabel || label
    source.clear()
    if (!loc) return
    const f = new Feature({ geometry: new Point(fromLonLat([loc.lon, loc.lat])) })
    f.setId('hq')
    f.setStyle(makeHQStyle(label))
    source.addFeature(f)
  }

  function setHQPlacementMode(on) {
    shell.setMode(HQ_MODE, on)
  }

  // Placement mode: the click reports where, nothing else happens.
  const offClick = shell.onClick((evt) => {
    const [lon, lat] = toLonLat(evt.coordinate)
    ctx.onHQPlaced?.({ lat, lon })
    return true
  }, { mode: HQ_MODE, id: 'settings-hq-place' })

  return { api: { setHQ, setHQPlacementMode }, dispose: offClick }
}

export default {
  name: 'settings',
  layers: { [HQ_LAYER.id]: createHQLayer },
  setup: setupHQMap,
}
