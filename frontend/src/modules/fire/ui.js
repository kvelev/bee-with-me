// Fire map UI state that outlives a component: layer switches and (for T508) the open dialog.
// No OpenLayers here: the manifest imports this file statically (rule `manifest-reaches-no-openlayers`).
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useFireStore } from './store.js'

export const useFireUi = defineStore('fireUi', () => {
  const dialog = ref(null)   // { kind: 'report' | 'zone', target } | null, used from T508 on

  // Flips the flag; the map panel's watcher shows or hides the layer in the same tick.
  // The fetch a layer needs starts in the store. Its failures drive fetchFailed / zonesFailed, so none is thrown here.
  function setLayer(name, on) {
    return useFireStore().setLayer(name, on).catch(() => { /* fetchFailed / zonesFailed drive the notices */ })
  }

  // A new report or zone must be visible where it was just made: switch its layer on if it is off.
  function ensureLayer(name) {
    if (!useFireStore().layers[name]) setLayer(name, true)
  }

  function openDialog(next) { dialog.value = next }
  function closeDialog() { dialog.value = null }

  return { dialog, setLayer, ensureLayer, openDialog, closeDialog }
})
