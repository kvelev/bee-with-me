import { describe, it, expect, vi, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import FirePopup from './FirePopup.vue'
import { i18n } from '../../../i18n/index.js'

const mountPopup = (kind, properties) =>
  mount(FirePopup, { props: { kind, properties }, global: { plugins: [i18n] } })

describe('FirePopup unknown values', () => {
  it('burnt area with null area and dates shows unknown, never 0 ha or 1970 [B32]', () => {
    const text = mountPopup('burnt_area', { id: 'x', area_ha: null, started_at: null, ended_at: null }).text()
    expect(text).not.toContain('1970')
    expect(text).not.toContain('0 ha')
    expect(text).not.toContain('burned')
    expect(text.match(/unknown/g)).toHaveLength(3)
  })

  it('empty string and undefined count as unknown too [B32]', () => {
    const text = mountPopup('burnt_area', { id: 'x', area_ha: '', started_at: undefined, ended_at: '' }).text()
    expect(text).not.toContain('1970')
    expect(text).not.toContain('0 ha')
  })

  it('a real zero area still reads as 0 ha [B32]', () => {
    const text = mountPopup('burnt_area', { id: 'x', area_ha: 0, started_at: '2026-10-01T00:00:00Z', ended_at: null }).text()
    expect(text).toContain('0 ha')
  })

  it('hotspot with null acquired_at shows unknown and no epoch time [B32]', () => {
    const text = mountPopup('hotspot', { id: 'x', source: 'viirs', acquired_at: null }).text()
    expect(text).not.toContain('1970')
    expect(text).toContain('unknown')
  })

  it('an unknown state renders the unknown text, not the raw i18n key [B32]', () => {
    const text = mountPopup('hotspot', { id: 'x', source: 'viirs', acquired_at: null, state: 'weird' }).text()
    expect(text).not.toContain('fire.state')
    expect(text).not.toContain('weird')
    expect(text.match(/unknown/g).length).toBeGreaterThanOrEqual(2)
  })

  it('known states still render their label [B32]', () => {
    const text = mountPopup('hotspot', { id: 'x', source: 'viirs', acquired_at: '2026-10-01T00:00:00Z', state: 'dismissed' }).text()
    expect(text).toContain('Dismissed')
  })
})

describe('FirePopup coordinates', () => {
  const mountAt = (kind, lonLat) =>
    mount(FirePopup, { props: { kind, properties: { id: 'x', source: 'viirs', acquired_at: '2026-10-01T00:00:00Z' }, lonLat }, global: { plugins: [i18n] }, attachTo: document.body })

  afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); delete navigator.clipboard })

  it('hotspot shows lat, lon with 5 decimals and an MGRS row [COORDS]', () => {
    const w = mountAt('hotspot', [23.3219, 42.69751])
    expect(w.text()).toContain('Coordinates')
    expect(w.get('[data-testid="fp-latlon"]').text()).toBe('42.69751, 23.32190')
    expect(w.get('[data-testid="fp-mgrs"]').text()).toMatch(/^34T[A-Z]{2}\d{10}$/)
  })

  it('burnt area labels the coordinates as the clicked point [COORDS]', () => {
    const w = mountAt('burnt_area', [25.5, 42.25])
    expect(w.text()).toContain('Clicked point')
    expect(w.get('[data-testid="fp-latlon"]').text()).toBe('42.25000, 25.50000')
  })

  it('no coordinates row without lonLat [COORDS]', () => {
    expect(mountAt('hotspot', null).find('[data-testid="fp-latlon"]').exists()).toBe(false)
  })

  it('copy writes the exact text and announces Copied [COORDS]', async () => {
    const writeText = vi.fn().mockResolvedValue()
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    const w = mountAt('hotspot', [23.3219, 42.69751])
    await w.get('[data-testid="fp-copy-latlon"]').trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('42.69751, 23.32190')
    expect(w.get('[data-testid="fp-copy-status"]').attributes('aria-live')).toBe('polite')
    expect(w.get('[data-testid="fp-copy-status"]').text()).toBe('Copied')
  })

  it('a rejected clipboard write falls back, and failure shows Copy failed [COORDS]', async () => {
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: vi.fn().mockRejectedValue(new Error('denied')) }, configurable: true })
    document.execCommand = vi.fn().mockReturnValue(false)
    const w = mountAt('hotspot', [23.3219, 42.69751])
    await w.get('[data-testid="fp-copy-latlon"]').trigger('click')
    await flushPromises()
    expect(w.get('[data-testid="fp-copy-status"]').text()).toBe('Copy failed')
  })

  it('without navigator.clipboard it uses a hidden textarea and execCommand [COORDS]', async () => {
    let copied = null
    document.execCommand = vi.fn(() => { copied = document.activeElement?.value ?? document.querySelector('textarea')?.value; return true })
    const w = mountAt('hotspot', [23.3219, 42.69751])
    await w.get('[data-testid="fp-copy-latlon"]').trigger('click')
    await flushPromises()
    expect(document.execCommand).toHaveBeenCalledWith('copy')
    expect(copied).toBe('42.69751, 23.32190')
    expect(document.querySelector('textarea')).toBeNull()
    expect(w.get('[data-testid="fp-copy-status"]').text()).toBe('Copied')
  })
})

const HOSTILE = '<img src=x onerror="window.__pwned = true">'
const mountActions = (props) => mount(FirePopup, { props: { kind: 'hotspot', ...props }, global: { plugins: [i18n] } })

describe('FirePopup actions', () => {
  it('renders user-typed notes as text, never as markup [T19]', () => {
    const wrapper = mountActions({
      isAdmin: true,
      properties: { id: 'r1', source: 'field_report', state: 'active', acquired_at: '2026-10-02T09:00:00+00:00',
                    notes: HOSTILE, dismiss_notes: HOSTILE },
    })
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.text()).toContain(HOSTILE)
    expect(window.__pwned).toBeUndefined()
  })

  it('emits the admin actions [T19]', async () => {
    const wrapper = mountActions({
      isAdmin: true,
      properties: { id: 'h1', source: 'viirs', state: 'active', acquired_at: '2026-10-02T09:00:00+00:00' },
    })
    await wrapper.find('[data-action="dismiss"]').trigger('click')
    await wrapper.find('[data-action="create-zone"]').trigger('click')
    expect(Object.keys(wrapper.emitted())).toEqual(expect.arrayContaining(['dismiss', 'create-zone']))
    expect(wrapper.emitted().dismiss[0][0]).toEqual({ id: 'h1', notes: null })
  })

  it('hides admin actions from non-admins and offers Extinguish on field reports [T19]', () => {
    const wrapper = mountActions({
      isAdmin: false,
      properties: { id: 'r1', source: 'field_report', state: 'active', acquired_at: '2026-10-02T09:00:00+00:00' },
    })
    expect(wrapper.find('[data-action="dismiss"]').exists()).toBe(false)
    expect(wrapper.find('[data-action="create-zone"]').exists()).toBe(false)
    expect(wrapper.find('[data-action="extinguish"]').exists()).toBe(true)
  })

  it('a satellite detection has no Extinguish, an extinguished report has none either [T19]', () => {
    const sat = mountActions({ isAdmin: true, properties: { id: 'h1', source: 'viirs', state: 'active' } })
    expect(sat.find('[data-action="extinguish"]').exists()).toBe(false)
    const done = mountActions({ isAdmin: true, properties: { id: 'r1', source: 'field_report', state: 'extinguished' } })
    expect(done.find('[data-action="extinguish"]').exists()).toBe(false)
  })

  it('an optional note travels with Dismiss, trimmed; an empty one is null [T19]', async () => {
    const wrapper = mountActions({ isAdmin: true, properties: { id: 'h1', source: 'viirs', state: 'active' } })
    expect(wrapper.find('[data-testid="fp-note"]').exists()).toBe(false)
    await wrapper.find('[data-action="toggle-note"]').trigger('click')
    const box = wrapper.find('[data-testid="fp-note"]')
    expect(box.attributes('maxlength')).toBe('1000')
    await box.setValue('  solar farm  ')
    await wrapper.find('[data-action="dismiss"]').trigger('click')
    expect(wrapper.emitted().dismiss[0][0]).toEqual({ id: 'h1', notes: 'solar farm' })
  })

  it('create-zone emits the point of the detection [T19]', async () => {
    const wrapper = mount(FirePopup, {
      props: { kind: 'hotspot', isAdmin: true, lonLat: [24.5, 42.5], properties: { id: 'h1', source: 'viirs', state: 'active' } },
      global: { plugins: [i18n] },
    })
    await wrapper.find('[data-action="create-zone"]').trigger('click')
    expect(wrapper.emitted()['create-zone'][0][0]).toEqual({ latitude: 42.5, longitude: 24.5 })
  })

  it('busy disables the actions and an error shows as text [T19]', () => {
    const wrapper = mountActions({
      isAdmin: true, busy: true, errorText: HOSTILE,
      properties: { id: 'h1', source: 'viirs', state: 'active' },
    })
    expect(wrapper.find('[data-action="dismiss"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.get('[data-testid="fp-error"]').text()).toBe(HOSTILE)
  })

  it('an already dismissed detection offers no second Dismiss [T19]', () => {
    const wrapper = mountActions({ isAdmin: true, properties: { id: 'h1', source: 'viirs', state: 'dismissed' } })
    expect(wrapper.find('[data-action="dismiss"]').exists()).toBe(false)
  })

  it('burnt areas have no actions [T19]', () => {
    const wrapper = mount(FirePopup, { props: { kind: 'burnt_area', isAdmin: true, properties: { id: 'b1' } }, global: { plugins: [i18n] } })
    expect(wrapper.find('.fp-actions').exists()).toBe(false)
  })
})
