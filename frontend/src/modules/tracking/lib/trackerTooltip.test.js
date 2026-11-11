import { describe, it, expect, beforeEach } from 'vitest'
import { renderTrackerTooltip } from './trackerTooltip'
import { clearPhotoCache } from './photoMarker'

// A photo shows only when the shared cache has it loaded (B56): an Image stub that loads at once.
beforeEach(() => {
  clearPhotoCache()
  globalThis.Image = class { set src(v) { this._src = v; this.onload?.() } get src() { return this._src } }
})

const EVIL = '<img src=x onerror=alert(1)>'

describe('tracker tooltip', () => {
  it('team tooltip shows names, rank, description and members as literal text [B52]', () => {
    const el = document.createElement('div')
    renderTrackerTooltip(el, {
      displayLabel: EVIL, full_name: EVIL, rank: '<b>cpt</b>', mgrs: '35TLG1', sos_active: true,
    }, {
      description: '<script>alert(2)</script><img src=y onerror=alert(3)>',
      members: [{ full_name: EVIL, rank: EVIL, is_leader: true }, { full_name: '<svg onload=alert(4)>', is_leader: false }],
    })
    expect(el.querySelector('img, script, svg, b')).toBeNull()
    expect(el.textContent).toContain(EVIL)
    expect(el.textContent).toContain('<script>alert(2)</script>')
    expect(el.textContent).toContain('<svg onload=alert(4)>')
    expect(el.textContent).toContain('SOS')
    expect(el.querySelector('strong').textContent).toBe(EVIL)
  })

  it('individual tooltip renders name, phone and device name as text and keeps the facts [B52]', () => {
    const el = document.createElement('div')
    renderTrackerTooltip(el, {
      device_name: EVIL, dev_sn: 7, phone: EVIL, mgrs: '35TLG2', altitude_m: 812, battery_voltage: 3.94,
      repeater_mode: true, recorded_at: '2026-10-04T10:00:00Z',
    }, null)
    expect(el.querySelector('img')).toBeNull()
    expect(el.querySelector('strong').textContent).toBe(EVIL)
    const t = el.textContent
    expect(t).toContain(`📞 ${EVIL}`)
    expect(t).toContain('⛰ 812 m')
    expect(t).toContain('🔋 3.9 V')
    expect(t).toContain('Repeater')
    expect(t).toContain('35TLG2')
  })

  it('a second render replaces the first [B52]', () => {
    const el = document.createElement('div')
    renderTrackerTooltip(el, { full_name: 'A', dev_sn: 1 }, null)
    renderTrackerTooltip(el, { full_name: 'B', dev_sn: 2 }, null)
    expect(el.textContent).not.toContain('A')
    expect(el.textContent).toContain('B')
  })

  describe('photo [PHOTO-TIP]', () => {
    const base = { full_name: 'Ivan', dev_sn: 1, mgrs: '35TLG1', photo_url: '/uploads/a.jpg', received_at: new Date().toISOString() }
    const render = (pos, opts, gd = null) => {
      const el = document.createElement('div')
      renderTrackerTooltip(el, pos, gd, opts)
      return el
    }

    it('shows the photo with the flag on and a same-origin URL, alt from the name [PHOTO-TIP]', () => {
      const img = render(base).querySelector('img.tt-photo')
      expect(img).not.toBeNull()
      expect(img.getAttribute('src')).toBe('/uploads/a.jpg')
      expect(img.alt).toBe('Ivan')
      expect(img.classList.contains('tt-photo--sos')).toBe(false)
    })

    it('is hidden with the flag off, no URL, a cross-origin or a javascript: URL [PHOTO-TIP]', () => {
      expect(render(base, { showPhotos: false }).querySelector('img')).toBeNull()
      expect(render({ ...base, photo_url: null }).querySelector('img')).toBeNull()
      for (const u of ['https://cdn.example/a.jpg', '//cdn.example/a.jpg', 'javascript:alert(1)', 'data:image/png;base64,AAAA']) {
        expect(render({ ...base, photo_url: u }).querySelector('img')).toBeNull()
      }
      expect(render({ ...base, photo_url: null }).textContent).toContain('Ivan')
    })

    it('a hostile name stays text and becomes the alt value [PHOTO-TIP]', () => {
      const el = render({ ...base, full_name: EVIL })
      expect(el.querySelectorAll('img')).toHaveLength(1)
      expect(el.querySelector('strong').textContent).toBe(EVIL)
      expect(el.querySelector('img').alt).toBe(EVIL)
    })

    it('SOS adds the red ring class, stale dims [PHOTO-TIP]', () => {
      expect(render({ ...base, sos_active: true }).querySelector('img').classList.contains('tt-photo--sos')).toBe(true)
      const old = new Date(Date.now() - 20 * 60 * 1000).toISOString()
      expect(render({ ...base, received_at: old }).querySelector('img').classList.contains('tt-photo--stale')).toBe(true)
    })

    it('a load error removes the image silently [PHOTO-TIP]', () => {
      const el = render(base)
      el.querySelector('img').onerror()
      expect(el.querySelector('img')).toBeNull()
      expect(el.textContent).toContain('Ivan')
    })

    it('team tooltip: one photo for the hovered person, none for members [PHOTO-TIP]', () => {
      const el = render({ ...base, displayLabel: 'Alpha' }, undefined, {
        members: [{ full_name: 'A', photo_url: '/uploads/b.jpg' }, { full_name: 'B', photo_url: '/uploads/c.jpg' }],
      })
      expect(el.querySelectorAll('img')).toHaveLength(1)
    })
  })
})
