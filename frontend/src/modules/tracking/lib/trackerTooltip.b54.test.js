import { describe, it, expect, beforeEach } from 'vitest'
import { renderTrackerTooltip } from './trackerTooltip'
import { clearPhotoCache } from './photoMarker'

// The tooltip shows a photo only when the shared cache has it loaded (B56): an Image stub that
// loads at once stands in for a photo that is already cached.
beforeEach(() => {
  clearPhotoCache()
  globalThis.Image = class { set src(v) { this._src = v; this.onload?.() } get src() { return this._src } }
})

const base = { full_name: 'Ivan', dev_sn: 1, mgrs: '35TLG1', photo_url: '/uploads/a.jpg', sos_active: true }
const render = (pos) => { const el = document.createElement('div'); renderTrackerTooltip(el, pos, null); return el }

describe('tooltip photo of a quiet SOS [B54]', () => {
  it('live SOS: red ring on the image, not dimmed [B54]', () => {
    const el = render({ ...base, received_at: new Date().toISOString() })
    const img = el.querySelector('img')
    expect(img.classList.contains('tt-photo--sos')).toBe(true)
    expect(img.classList.contains('tt-photo--stale')).toBe(false)
    expect(el.querySelector('.tt-photo-ring')).toBeNull()
  })
  it('SOS silent over 30 min: ring on a wrapper, photo dimmed [B54]', () => {
    const el = render({ ...base, received_at: new Date(Date.now() - 45 * 60_000).toISOString() })
    const img = el.querySelector('.tt-photo-ring > img')
    expect(img.classList.contains('tt-photo--sos')).toBe(true)
    expect(img.classList.contains('tt-photo--stale')).toBe(true)
    img.onerror()
    expect(el.querySelector('.tt-photo-ring')).toBeNull()
  })
})
