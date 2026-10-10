import { ref } from 'vue'
import { getTileStatus } from '../api'

// BG Mountains tiles: offline (downloaded to this server, /tiles/bgmountains) or online (bgmtile.kade.si).
// A choice made on the About or Settings page is kept per browser. Until someone chooses, the map
// uses the offline tiles only if this server actually has them, so a server without a download
// shows the online map instead of an empty one.
const STORAGE_KEY = 'bgMountainsOffline'

function storedChoice() {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    return v === null ? null : v !== 'false'
  } catch {
    return null
  }
}

const initial = storedChoice()
let explicit = initial !== null
const bgMountainsOffline = ref(initial ?? false)

export function setBgMountainsOffline(offline) {
  explicit = true
  bgMountainsOffline.value = offline
  try { localStorage.setItem(STORAGE_KEY, String(offline)) } catch { /* private mode: this session only */ }
}

let resolving = null
/** Pick the default from the server once, unless the user already chose. Safe to call often. */
export function resolveBgMountainsDefault() {
  if (explicit) return Promise.resolve()
  resolving ??= (async () => {
    try {
      const status = await getTileStatus()
      if (!explicit) bgMountainsOffline.value = !!status?.available
    } catch {
      resolving = null   // not logged in yet, or the server is unreachable: try again next time
    }
  })()
  return resolving
}

export function useSettings() {
  return { bgMountainsOffline, setBgMountainsOffline, resolveBgMountainsDefault }
}
