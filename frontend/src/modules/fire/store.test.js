import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('../../api', () => ({
  getFireHotspots:   vi.fn(),
  getFireBurntAreas: vi.fn(),
  getFireStatus:     vi.fn(),
}))

import { getFireHotspots, getFireBurntAreas } from '../../api'
import { useFireStore } from './store.js'
import { firePillState } from './lib/fireStyle'

const FC = (n, extra = {}) => ({ type: 'FeatureCollection', features: Array.from({ length: n }, (_, i) => ({ id: String(i) })), ...extra })

describe('useFireStore', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    vi.clearAllMocks()
    getFireHotspots.mockResolvedValue(FC(2, { fetched_at: '2026-10-02T10:00:00+00:00', upstream_state: 'live' }))
    getFireBurntAreas.mockResolvedValue(FC(1))
  })

  it('starts with every layer off and nothing loaded [T11]', () => {
    const store = useFireStore()
    expect(store.layers).toEqual({ burnt: false, hotspots: false, zones: false })
    expect(store.anyLayerOn).toBe(false)
    expect(store.hotspots.features).toEqual([])
  })

  it('turning a layer on fetches only that layer and remembers it [T11]', async () => {
    const store = useFireStore()
    await store.setLayer('hotspots', true)
    expect(getFireHotspots).toHaveBeenCalledTimes(1)
    expect(getFireBurntAreas).not.toHaveBeenCalled()
    expect(store.hotspots.features).toHaveLength(2)
    expect(store.fetchedAt).toBe('2026-10-02T10:00:00+00:00')
    expect(store.upstreamState).toBe('live')
    expect(JSON.parse(localStorage.getItem('bwm.fireLayers'))).toEqual({ burnt: false, hotspots: true, zones: false })
  })

  it('restores layer state from localStorage and survives garbage in it [T11]', () => {
    localStorage.setItem('bwm.fireLayers', JSON.stringify({ burnt: true }))
    expect(useFireStore().layers).toEqual({ burnt: true, hotspots: false, zones: false })
    setActivePinia(createPinia())
    localStorage.setItem('bwm.fireLayers', '{not json')
    expect(useFireStore().layers).toEqual({ burnt: false, hotspots: false, zones: false })
  })

  it('fire_data_updated refetches only visible layers [T11]', async () => {
    const store = useFireStore()
    await store.setLayer('burnt', true)
    vi.clearAllMocks()
    getFireBurntAreas.mockResolvedValue(FC(3))
    await store.applyFireDataUpdated({ fetched_at: '2026-10-02T11:00:00+00:00', upstream_state: 'error' })
    expect(getFireBurntAreas).toHaveBeenCalledTimes(1)
    expect(getFireHotspots).not.toHaveBeenCalled()
    expect(store.burntAreas.features).toHaveLength(3)
  })

  it('a failed fetch keeps the previous data [T11]', async () => {
    const store = useFireStore()
    await store.setLayer('hotspots', true)
    getFireHotspots.mockRejectedValueOnce('Network Error')
    await expect(store.refreshVisible()).rejects.toBe('Network Error')
    expect(store.hotspots.features).toHaveLength(2)
  })

  it('tracks the burnt feed as-of time and the shown (visible-only, pessimistic) pair [B33]', async () => {
    const store = useFireStore()
    getFireBurntAreas.mockResolvedValue(FC(1, { fetched_at: '2026-10-02T09:00:00+00:00', upstream_state: 'no_recent_detections' }))
    await store.setLayer('burnt', true)
    expect(store.burntFetchedAt).toBe('2026-10-02T09:00:00+00:00')
    expect(store.burntUpstreamState).toBe('no_recent_detections')
    // Only burnt is on: the pill shows burnt's time, not hotspots' (never fetched).
    expect(store.shownFetchedAt).toBe('2026-10-02T09:00:00+00:00')
    expect(store.shownUpstreamState).toBe('no_recent_detections')
    await store.setLayer('hotspots', true)
    // Both on: oldest time, worst state.
    expect(store.shownFetchedAt).toBe('2026-10-02T09:00:00+00:00')
    expect(store.shownUpstreamState).toBe('no_recent_detections')
    getFireHotspots.mockResolvedValue(FC(2, { fetched_at: '2026-10-02T08:00:00+00:00', upstream_state: 'error' }))
    await store.refreshVisible()
    expect(store.shownFetchedAt).toBe('2026-10-02T08:00:00+00:00')
    expect(store.shownUpstreamState).toBe('error')
  })

  it('fetchFailed is set by a failure on a shown layer and cleared by the next success [B33]', async () => {
    const store = useFireStore()
    await store.setLayer('hotspots', true)
    expect(store.fetchFailed).toBe(false)
    getFireHotspots.mockRejectedValueOnce('Network Error')
    await expect(store.refreshVisible()).rejects.toBe('Network Error')
    expect(store.fetchFailed).toBe(true)
    await store.refreshVisible()
    expect(store.fetchFailed).toBe(false)
  })

  it('an older response arriving last does not overwrite newer data [B33]', async () => {
    const store = useFireStore()
    await store.setLayer('hotspots', true)
    const old = deferred(), fresh = deferred()
    getFireHotspots.mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise)
    const a = store.refreshVisible()
    const b = store.applyFireDataUpdated({ fetched_at: '2026-10-03T09:00:00Z', upstream_state: 'live' })
    fresh.resolve(FC(9, { fetched_at: '2026-10-03T09:00:00Z', upstream_state: 'live' }))
    await b
    old.resolve(FC(1, { fetched_at: '2026-10-03T08:30:00Z', upstream_state: 'live' }))
    await a
    expect(store.hotspots.features).toHaveLength(9)
    expect(store.fetchedAt).toBe('2026-10-03T09:00:00Z')
  })

  it('a late failure of an older request does not mark current data as failed [B33]', async () => {
    const store = useFireStore()
    await store.setLayer('hotspots', true)
    const old = deferred()
    getFireHotspots.mockReturnValueOnce(old.promise).mockResolvedValueOnce(FC(2, { fetched_at: '2026-10-03T09:00:00Z', upstream_state: 'live' }))
    const a = store.refreshVisible().catch(() => {})
    await store.refreshVisible()
    old.reject('timeout')
    await a
    expect(store.fetchFailed).toBe(false)
    expect(store.hotspots.features).toHaveLength(2)
  })

  it('a failure after its layer was turned off leaves no failed flag behind [B33]', async () => {
    const store = useFireStore()
    const d = deferred()
    getFireHotspots.mockReturnValueOnce(d.promise)
    const p = store.setLayer('hotspots', true).catch(() => {})
    await store.setLayer('hotspots', false)
    d.reject('boom')
    await p
    expect(store.fetchFailed).toBe(false)
    // Turning another layer off later must not resurrect it either.
    await store.setLayer('burnt', false)
    expect(store.fetchFailed).toBe(false)
    // And a response arriving after the layer was hidden is dropped.
    const e = deferred()
    getFireHotspots.mockReturnValueOnce(e.promise)
    const q = store.setLayer('hotspots', true)
    await store.setLayer('hotspots', false)
    e.resolve(FC(5, { fetched_at: '2026-10-03T09:00:00Z', upstream_state: 'live' }))
    await q
    expect(store.hotspots.features).toHaveLength(0)
  })

  it('each feed fails independently and fetchFailed ignores a hidden layer [B33]', async () => {
    const store = useFireStore()
    await store.setLayer('hotspots', true)
    await store.setLayer('burnt', true)
    getFireBurntAreas.mockRejectedValueOnce('boom')
    await expect(store.refreshVisible()).rejects.toBe('boom')
    expect(store.fetchFailed).toBe(true)
    expect(store.hotspots.features).toHaveLength(2)
    await store.setLayer('burnt', false)
    expect(store.fetchFailed).toBe(false)
  })
  it('markFeedFailed flags a shown feed until the next good fetch [B34]', async () => {
    const store = useFireStore()
    await store.setLayer('hotspots', true)
    store.markFeedFailed('hotspots')
    expect(store.fetchFailed).toBe(true)
    await store.refreshVisible()
    expect(store.fetchFailed).toBe(false)
  })

  const pillOf = (s) => firePillState({
    at: s.shownFetchedAt, upstreamState: s.shownUpstreamState, failed: s.fetchFailed, nowMs: Date.parse('2026-10-03T09:05:00Z'),
  })

  it('a WS update while the layer is off does not become the pill time of a later failed fetch [B35]', async () => {
    const store = useFireStore()
    await store.applyFireDataUpdated({ fetched_at: '2026-10-03T09:00:00Z', upstream_state: 'live' })
    getFireHotspots.mockRejectedValueOnce(new Error('503'))
    await store.setLayer('hotspots', true).catch(() => {})
    expect(store.hotspots.features).toHaveLength(0)
    expect(pillOf(store)).toEqual({ kind: 'error', noteKey: 'fire.errorNoData' })
  })

  it('a failed refetch after a WS update keeps the time of the data on the map [B35]', async () => {
    const store = useFireStore()
    getFireHotspots.mockResolvedValueOnce(FC(3, { fetched_at: '2026-10-03T08:30:00Z', upstream_state: 'live' }))
    await store.setLayer('hotspots', true)
    getFireHotspots.mockRejectedValueOnce(new Error('503'))
    await store.applyFireDataUpdated({ fetched_at: '2026-10-03T09:00:00Z', upstream_state: 'live' }).catch(() => {})
    expect(store.shownFetchedAt).toBe('2026-10-03T08:30:00Z')
    expect(pillOf(store)).toEqual({ kind: 'error', noteKey: 'fire.error' })
  })

  it('an unreadable payload keeps the previous time and marks the feed failed [B35]', async () => {
    const store = useFireStore()
    getFireHotspots.mockResolvedValueOnce(FC(1, { fetched_at: '2026-10-03T08:30:00Z', upstream_state: 'live' }))
    await store.setLayer('hotspots', true)
    getFireHotspots.mockResolvedValueOnce(FC(1, { fetched_at: '2026-10-03T09:00:00Z', upstream_state: 'live' }))
    await store.refreshVisible()
    store.markFeedFailed('hotspots')           // the map rejected the 09:00 payload
    expect(store.shownFetchedAt).toBe('2026-10-03T08:30:00Z')
    expect(store.fetchFailed).toBe(true)
  })

  it('an unreadable first payload leaves no time at all [B35]', async () => {
    const store = useFireStore()
    await store.setLayer('burnt', true)        // FC(1) without fetched_at
    getFireBurntAreas.mockResolvedValueOnce(FC(1, { fetched_at: '2026-10-03T09:00:00Z', upstream_state: 'live' }))
    await store.refreshVisible()
    store.markFeedFailed('burnt')
    expect(store.burntFetchedAt).toBe(null)
  })

  it('retryFailed refetches only shown feeds whose flag is set [B35]', async () => {
    const store = useFireStore()
    await store.setLayer('hotspots', true)
    await store.setLayer('burnt', true)
    vi.clearAllMocks()
    await store.retryFailed()
    expect(getFireHotspots).not.toHaveBeenCalled()
    expect(getFireBurntAreas).not.toHaveBeenCalled()
    store.markFeedFailed('burnt')
    await store.retryFailed()
    expect(getFireHotspots).not.toHaveBeenCalled()
    expect(getFireBurntAreas).toHaveBeenCalledTimes(1)
    expect(store.fetchFailed).toBe(false)
    getFireHotspots.mockRejectedValueOnce(new Error('503'))
    await store.refreshVisible().catch(() => {})
    await store.setLayer('hotspots', false)    // hidden feed is not retried
    vi.clearAllMocks()
    await store.retryFailed()
    expect(getFireHotspots).not.toHaveBeenCalled()
  })
})

function deferred() {
  let resolve, reject
  const promise = new Promise((a, b) => { resolve = a; reject = b })
  return { promise, resolve, reject }
}
