import { ref, watch } from 'vue'

const bgMountainsOffline = ref(localStorage.getItem('bgMountainsOffline') !== 'false')

watch(bgMountainsOffline, v => localStorage.setItem('bgMountainsOffline', String(v)))

export function useSettings() {
  return { bgMountainsOffline }
}
