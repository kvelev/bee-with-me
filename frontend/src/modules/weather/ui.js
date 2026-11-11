// Weather UI state that outlives a component: which overlay is on. The toolbar flips it, the panel reacts.
// No OpenLayers here: the manifest imports this file statically (rule `manifest-reaches-no-openlayers`).
import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useWeatherUi = defineStore('weatherUi', () => {
  const layerId = ref(null)   // null | 'clouds_new' | 'precipitation_new' | 'wind_new' | 'temp_new'

  // The same button again switches the overlay off.
  function toggle(id) {
    layerId.value = layerId.value === id ? null : id
  }

  return { layerId, toggle }
})
