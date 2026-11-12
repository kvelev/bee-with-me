import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia, storeToRefs } from 'pinia'
import { nextTick, watch } from 'vue'
import { useTrackingStore } from './store.js'
import { useTrackerUi } from './ui.js'

const NOW = Date.parse('2026-06-01T12:00:00.000Z')
const pos = (id, over = {}) => ({
  device_id: id, dev_sn: 1, full_name: id, mgrs: '35TLG1', latitude: 42.5, longitude: 24.5,
  received_at: new Date(NOW - 1000).toISOString(), groups: [], rank: '', ...over,
})

function setup(list) {
  setActivePinia(createPinia())
  const tracking = useTrackingStore()
  tracking.positions = Object.fromEntries(list.map((p) => [p.device_id, p]))
  return { tracking, ui: useTrackerUi() }
}

beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(NOW) })
afterEach(() => { vi.useRealTimers() })

describe('useTrackerUi', () => {
  it('displayList follows the rank filter [T631]', () => {
    const { ui } = setup([pos('a', { rank: 'Captain' }), pos('b', { rank: 'Private' })])
    expect(ui.displayList.map((p) => p.device_id).sort()).toEqual(['a', 'b'])
    ui.rankFilter = 'capt'
    expect(ui.displayList.map((p) => p.device_id)).toEqual(['a'])
  })

  it('the teams view gives one leader row per team [T631]', () => {
    const g1 = { id: 'g1', name: 'Alpha', color: '#fff', is_leader: true }
    const { ui } = setup([
      pos('a', { groups: [g1] }),
      pos('b', { groups: [{ ...g1, is_leader: false }] }),
    ])
    ui.viewMode = 'groups'
    expect(ui.displayList.map((p) => p.device_id)).toEqual(['a'])
    expect(ui.displayList[0].displayLabel).toBe('Alpha')
    expect(ui.groupsWithLeaders).toHaveLength(1)
    expect(ui.groupsWithLeaders[0].leader.device_id).toBe('a')
  })

  it('select sets the selected device [T631]', () => {
    const { ui } = setup([pos('a')])
    ui.select('a')
    expect(ui.selectedDeviceId).toBe('a')
    ui.select(null)
    expect(ui.selectedDeviceId).toBeNull()
  })

  it('a device that left the list cannot stay selected [T631]', async () => {
    const { ui, tracking } = setup([pos('a'), pos('b')])
    ui.select('a')
    tracking.positions = { b: pos('b') }
    await nextTick()
    expect(ui.selectedDeviceId).toBeNull()
  })

  it('the order of displayList changes with the tick, without a new message [T631]', () => {
    // Both timestamps are ahead of the clock (device clock skew), so both ages are clamped to 0 and the list keeps
    // its insertion order. Once the clock passes the earlier one, that row has an age and rises, with no message.
    const { ui } = setup([
      pos('a', { received_at: new Date(NOW + 18_000).toISOString() }),
      pos('b', { received_at: new Date(NOW + 5_000).toISOString() }),
    ])
    expect(ui.displayList.map((p) => p.device_id)).toEqual(['a', 'b'])
    ui.startTick()
    vi.advanceTimersByTime(10_000)
    expect(ui.displayList.map((p) => p.device_id)).toEqual(['b', 'a'])
  })

  it('stopTick clears the interval [T631]', () => {
    const { ui } = setup([pos('a')])
    ui.startTick()
    ui.startTick()
    expect(vi.getTimerCount()).toBe(1)
    ui.stopTick()
    expect(vi.getTimerCount()).toBe(0)
    const at = ui.nowTick
    vi.advanceTimersByTime(30_000)
    expect(ui.nowTick).toBe(at)
  })

  it('reset puts mode, filter and selection back [T631]', () => {
    const { ui } = setup([pos('a')])
    ui.viewMode = 'groups'
    ui.rankFilter = 'x'
    ui.select('a')
    ui.groupsMap = { g: { id: 'g' } }
    ui.reset()
    expect(ui.viewMode).toBe('individuals')
    expect(ui.rankFilter).toBe('')
    expect(ui.selectedDeviceId).toBeNull()
    expect(ui.groupsMap).toEqual({})
  })

  it('the displayList taken with storeToRefs is a ref a watcher can follow [T631]', async () => {
    const { ui } = setup([pos('a', { rank: 'Captain' }), pos('b', { rank: 'Private' })])
    const { displayList } = storeToRefs(ui)
    const seen = vi.fn()
    watch(displayList, (l) => seen(l.map((p) => p.device_id)), { deep: true })
    ui.rankFilter = 'priv'
    await nextTick()
    expect(seen).toHaveBeenCalledWith(['b'])
  })
})
