// The four weather overlays of the map toolbar, with the legend each one draws. Plain data, no OpenLayers.
import { tempLegendGradient } from './lib/weatherTiles.js'

export const WEATHER_LAYERS = [
  {
    // Clouds and rain are recoloured from OWM's faint tiles (lib/weatherTiles.js); these legends
    // show that output: white rising with cover from 10 %, and the 0.1 / 1 / 5 / 20 mm/h rain scale.
    id: 'clouds_new',
    gradient: 'linear-gradient(to right, rgba(244,247,252,0) 0%, rgba(244,247,252,0.2) 20%, rgba(244,247,252,0.5) 60%, rgba(244,247,252,0.8) 100%)',
    stops: ['10%', '50%', '100%'],
  },
  {
    id: 'precipitation_new',
    gradient: 'linear-gradient(to right, rgba(160,216,239,0.55), rgba(65,105,225,0.75), rgba(0,0,205,0.85), rgba(102,0,204,0.9))',
    stops: ['0.1', '1', '5', '20 mm/h'],
  },
  {
    id: 'wind_new',
    gradient: 'linear-gradient(to right, #2c45e8, #54b5e6, #7bcb6b, #e8e04a, #e87b3b, #e83b2c)',
    stops: ['0', '5', '15', '30 m/s'],
  },
  {
    // Recoloured into 2 °C bands with contours (lib/weatherTiles.js); OWM's data stops at 30 °C.
    id: 'temp_new',
    gradient: tempLegendGradient(),
    stops: ['-20°', '5°', '30°C+'],   // evenly spaced labels on a linear −20 … 30 °C bar
  },
]
