import { describe, it, expect, beforeEach } from 'vitest'
import { renderTrackerTooltip } from './trackerTooltip'
import { clearPhotoCache, photoImage } from './photoMarker'

let loads
beforeEach(() => {
  clearPhotoCache(); loads = []
  globalThis.Image = class { set src(v) { this._src = v; loads.push(this) } get src() { return this._src } }
})
const pos = { full_name: 'Ivan', dev_sn: 1, mgrs: '35T', photo_url: '/uploads/broken.jpg', received_at: new Date().toISOString() }

describe('tooltip photo uses the shared cache [B56]', () => {
  it('a failed photo is not requested again on every pointermove, and no image box shows [B56]', () => {
    photoImage(pos.photo_url); loads[0].onerror()
    const tip = document.createElement('div')
    for (let i = 0; i < 30; i++) {
      renderTrackerTooltip(tip, pos, null)
      expect(tip.querySelector('img')).toBeNull()
    }
    expect(loads.length).toBe(1)
    expect(tip.textContent).toContain('Ivan')
  })
  it('shows the photo once the cache reports it loaded, and reuses one load [B56]', () => {
    const tip = document.createElement('div')
    renderTrackerTooltip(tip, pos, null)          // first hover warms the cache
    expect(tip.querySelector('img')).toBeNull()
    loads[0].onload()
    renderTrackerTooltip(tip, pos, null)
    expect(tip.querySelector('img.tt-photo')).not.toBeNull()
    expect(loads.length).toBe(1)
  })
})
