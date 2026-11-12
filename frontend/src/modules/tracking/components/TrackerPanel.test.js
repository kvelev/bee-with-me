import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia, storeToRefs } from 'pinia'
import { computed, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { i18n } from '../../../i18n/index.js'
import { useTrackingStore } from '../store.js'
import { useTrackerUi } from '../ui.js'
import TrackerPanel from './TrackerPanel.vue'

const NOW = Date.parse('2026-06-01T12:00:00.000Z')
const iso = (msAgo) => new Date(NOW - msAgo).toISOString()
const pos = (id, over = {}) => ({
  device_id: id, dev_sn: 1, full_name: `Name ${id}`, mgrs: `MGRS-${id}`, latitude: 42.5, longitude: 24.5,
  battery_voltage: 3.8, received_at: iso(1000), groups: [], rank: '', ...over,
})

let pinia, tracking, ui
const ctx = (over = {}) => ({
  hasSOS: ref(false),
  facade: { map: () => null, refreshMarkers: vi.fn() },
  mapKit: { fromLonLat: (c) => c },
  rowActions: [],
  ...over,
})
const show = (context = ctx()) => mount(TrackerPanel, { props: { context }, global: { plugins: [pinia, i18n] } })
const setPositions = (list) => { tracking.positions = Object.fromEntries(list.map((p) => [p.device_id, p])) }

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(NOW)
  pinia = createPinia()
  setActivePinia(pinia)
  i18n.global.locale.value = 'en'
  tracking = useTrackingStore()
  ui = useTrackerUi()
})
afterEach(() => { ui.stopTick(); vi.useRealTimers() })

describe('TrackerPanel', () => {
  it('rows come out by urgency and show name, MGRS, age and battery [T631]', () => {
    setPositions([pos('a', { received_at: iso(5_000) }), pos('b', { received_at: iso(120_000), battery_voltage: 3.2 })])
    const w = show()
    const rows = w.findAll('.tracker-row')
    expect(rows.map((r) => r.attributes('data-device-id'))).toEqual(['b', 'a'])
    expect(rows[0].text()).toContain('Name b')
    expect(rows[0].text()).toContain('MGRS-b')
    expect(rows[0].get('.tracker-age').text()).toBe('2m')
    expect(rows[0].get('.tracker-bat').text()).toBe('3.2V')
    expect(rows[0].get('.tracker-bat').classes()).toContain('bat-warn')
    w.unmount()
  })

  it('the rank filter narrows the rows and the list the map gets [T631]', async () => {
    setPositions([pos('a', { rank: 'Captain' }), pos('b', { rank: 'Private' })])
    const { displayList } = storeToRefs(ui)
    const forMap = computed(() => displayList.value.map((p) => p.device_id))   // the second consumer, as useMap
    const w = show()
    expect(w.findAll('.tracker-row')).toHaveLength(2)
    await w.get('.rank-input').setValue('priv')
    expect(w.findAll('.tracker-row').map((r) => r.attributes('data-device-id'))).toEqual(['b'])
    expect(forMap.value).toEqual(['b'])
    w.unmount()
  })

  it('the age label of a row changes class when its position goes stale, without a new message [T631]', async () => {
    setPositions([pos('a', { received_at: iso(9 * 60_000) })])
    ui.startTick()
    const w = show()
    expect(w.get('.tracker-age').classes()).not.toContain('age-stale')
    await vi.advanceTimersByTimeAsync(70_000)
    expect(w.get('.tracker-age').classes()).toContain('age-stale')
    expect(w.get('.tracker-row').classes()).toContain('fresh-stale')
    w.unmount()
  })

  it('a selected row offers the row actions of the modules and a click runs the action [T631]', async () => {
    setPositions([pos('a'), pos('b')])
    const onSelect = vi.fn()
    const w = show(ctx({
      rowActions: [{ id: 'x', target: 'tracker-row', order: 1, labelKey: 'fire.report.atPosition', testId: 'report-fire-row', onSelect }],
    }))
    expect(w.find('[data-testid="report-fire-row"]').exists()).toBe(false)
    await w.get('.tracker-row[data-device-id="a"]').trigger('click')
    expect(ui.selectedDeviceId).toBe('a')
    const btn = w.get('[data-testid="report-fire-row"]')
    expect(btn.text()).toBe('Report fire at this position')
    await btn.trigger('click')
    expect(onSelect).toHaveBeenCalledTimes(1)
    expect(onSelect.mock.calls[0][0]).toMatchObject({ deviceId: 'a', name: 'Name a', position: { device_id: 'a' } })
    expect(onSelect.mock.calls[0][0].ageMs).toBe(1000)
    w.unmount()
  })

  it('an action that is not available for the row is not offered [T631]', async () => {
    setPositions([pos('a')])
    const w = show(ctx({
      rowActions: [{ id: 'x', target: 'tracker-row', order: 1, labelKey: 'fire.report.atPosition', testId: 'no', isAvailable: () => false, onSelect() {} }],
    }))
    await w.get('.tracker-row').trigger('click')
    expect(w.find('[data-testid="no"]').exists()).toBe(false)
    w.unmount()
  })

  it('the tick keeps running when the panel is unmounted [T631]', () => {
    setPositions([pos('a')])
    ui.startTick()
    const w = show()
    w.unmount()
    expect(vi.getTimerCount()).toBe(1)
    const at = ui.nowTick
    vi.advanceTimersByTime(10_000)
    expect(ui.nowTick).toBe(at + 10_000)
  })

  it('shows the SOS badge from the context and the quiet silence notice [T631]', () => {
    setPositions([pos('a', { received_at: iso(15 * 60_000) })])
    const w = show(ctx({ hasSOS: ref(true) }))
    expect(w.find('.badge-sos').exists()).toBe(true)
    expect(w.find('.silence-notice').exists()).toBe(true)
    expect(w.find('.silence-notice').classes()).not.toContain('sos-pulse')
    w.unmount()
  })
})
