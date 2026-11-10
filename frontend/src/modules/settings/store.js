import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { getSettings, putHQ, putHQInitial, putSettings } from '../../api'
import { useAuthStore } from '../../stores/auth'
import { ApiError, detailOf } from '../../api/client'
import { photosOnMapOf } from './lib/settingsForm'

const LEGACY_HQ_KEY = 'bwm.hq'   // where MapView kept HQ before it moved to the database

function readLegacyHQ() {
  try {
    const parsed = JSON.parse(localStorage.getItem(LEGACY_HQ_KEY) || 'null')
    if (typeof parsed?.lat !== 'number' || typeof parsed?.lon !== 'number') return null
    return parsed
  } catch {
    return null
  }
}

function dropLegacyHQ() {
  try { localStorage.removeItem(LEGACY_HQ_KEY) } catch { /* nothing to drop */ }
}

// A legacy copy is worth keeping only when the failure says "try again later": no response at
// all (network, timeout, abort), a server-side error, or a missing settings row. Anything else
// (401, 403, 409, 422) is a verdict, and retrying the same value forever helps nobody.
export function isTransientFailure(err) {
  const status = err?.status
  return !status || status >= 500 || detailOf(err) === 'settings_missing'
}

// Store-level rejections that are not HTTP responses use the same shape.
function storeError(detail) {
  return new ApiError(detail, undefined)
}

export const useSettingsStore = defineStore('settings', () => {
  const settings = ref(null)

  const hq = computed(() => {
    const s = settings.value
    return s && s.hq_latitude != null ? { lat: s.hq_latitude, lon: s.hq_longitude } : null
  })

  // Missing in an old server response counts as on.
  const photosOnMap = computed(() => photosOnMapOf(settings.value))

  async function fetchSettings() {
    settings.value = await getSettings()
  }

  // Every write carries the version the client last saw, so a stale page can never overwrite
  // an alarm switch or a radius another admin changed since (BP-02). On a stale write the store
  // reloads the server state and rejects with 'settings_stale' so the page can say so.
  async function saveSettings(patch) {
    if (!settings.value) throw storeError('settings_missing')
    const { updated_at, ...current } = settings.value
    try {
      settings.value = await putSettings({ ...current, ...patch, expected_updated_at: updated_at })
    } catch (err) {
      if (detailOf(err) === 'settings_stale') {
        try { await fetchSettings() } catch { /* the page shows the stale message either way */ }
      }
      throw err
    }
  }

  // HQ writes touch only the HQ columns (PUT /settings/hq) and run one at a time, in click
  // order, so the last placement wins and the store ends up equal to what the server holds.
  let hqQueue = Promise.resolve()
  function writeHQ(lat, lon) {
    const run = async () => {
      settings.value = await putHQ({ hq_latitude: lat, hq_longitude: lon })
    }
    const result = hqQueue.then(run, run)
    hqQueue = result.catch(() => { /* the caller sees the failure; the queue goes on */ })
    return result
  }
  const setHQ   = (lat, lon) => writeHQ(lat, lon)
  const clearHQ = () => writeHQ(null, null)

  // One-time upload of the pre-database HQ from this browser. The database is the source of
  // truth: only an admin may seed it, and the local copy is dropped whenever it can no longer
  // be useful (non-admin, invalid, already set). It stays only for a transient failure.
  async function migrateLocalHQ() {
    const local = readLegacyHQ()
    if (!local) return 'skipped'
    const auth = useAuthStore()
    if (!auth.user) {
      try { await auth.fetchMe() } catch { return 'failed' }
    }
    if (auth.user?.role !== 'admin') {
      dropLegacyHQ()
      return 'dropped'
    }
    try {
      settings.value = await putHQInitial({ hq_latitude: local.lat, hq_longitude: local.lon })
      dropLegacyHQ()
      return 'uploaded'
    } catch (err) {
      if (detailOf(err) === 'hq_already_set') {
        dropLegacyHQ()
        return 'exists'
      }
      if (isTransientFailure(err)) return 'failed'
      dropLegacyHQ()
      return 'dropped'
    }
  }

  return { settings, hq, photosOnMap, fetchSettings, saveSettings, setHQ, clearHQ, migrateLocalHQ }
})
