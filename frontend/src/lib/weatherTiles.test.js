import { describe, it, expect } from 'vitest'
import { precipMm, cloudPct, recolorPrecip, recolorClouds, recolorFor } from './weatherTiles'

const px = (...rgba) => new Uint8ClampedArray(rgba)

describe('OWM weather tile decoding', () => {
  it('reads rain intensity from the blue channel (OWM palette)', () => {
    expect(precipMm(150, 150, 170, 2)).toBeCloseTo(0.2)
    expect(precipMm(119, 119, 190, 15)).toBeCloseTo(0.5)   // sampled from a real tile
    expect(precipMm(80, 80, 225, 180)).toBeCloseTo(10)
    expect(precipMm(0, 0, 0, 0)).toBe(0)
  })

  it('reads cloud cover from the red channel (OWM palette)', () => {
    expect(cloudPct(242, 241, 255, 127)).toBeCloseTo(90)    // sampled from a real tile
    expect(cloudPct(247, 247, 255, 127)).toBeCloseTo(50)
    expect(cloudPct(254, 254, 255, 2)).toBeLessThan(10)
  })
})

describe('recolouring', () => {
  it('makes drizzle clearly visible and heavy rain deep blue', () => {
    const drizzle = recolorPrecip(px(147, 147, 171, 1))     // real pixel: ~0.2 mm/h at 0.4 % opacity
    expect(drizzle[3]).toBeGreaterThan(130)
    const heavy = recolorPrecip(px(80, 80, 225, 180))       // 10 mm/h
    expect(heavy[2]).toBeGreaterThan(heavy[0])
    expect(heavy[3]).toBeGreaterThan(drizzle[3])
  })

  it('never paints rain red or green', () => {
    for (let b = 150; b <= 255; b += 5) {
      const [r, g, bb] = recolorPrecip(px(100, 100, b, 50))
      expect(bb).toBeGreaterThanOrEqual(Math.max(r, g))
    }
  })

  it('drops thin haze and makes thick cloud more opaque than OWM does', () => {
    expect(recolorClouds(px(254, 254, 255, 3))[3]).toBe(0)
    const thick = recolorClouds(px(242, 241, 255, 127))
    expect(thick[3]).toBeGreaterThan(127)
    const half = recolorClouds(px(247, 247, 255, 127))
    expect(half[3]).toBeLessThan(thick[3])
  })

  it('leaves transparent pixels and other layers alone', () => {
    expect([...recolorPrecip(px(0, 0, 0, 0))]).toEqual([0, 0, 0, 0])
    expect(recolorFor('wind_new')).toBeNull()
    expect(recolorFor('temp_new')).not.toBeNull()   // recoloured too (see 'temperature tiles')
    expect(recolorFor('clouds_new')).toBe(recolorClouds)
  })
})

describe('temperature tiles', async () => {
  const { tempC, recolorTemp, TEMP_BAND_C } = await import('./weatherTiles')

  it('decodes OWM temp_new colours (palette points and real samples)', () => {
    expect(tempC(35, 221, 221, 76)).toBeCloseTo(0)
    expect(tempC(255, 240, 40, 76)).toBeCloseTo(20)
    expect(tempC(255, 219, 40, 76)).toBeGreaterThan(21)      // real Sofia pixel; Open-Meteo said 21.5 °C
    expect(tempC(255, 219, 40, 76)).toBeLessThan(23)
    expect(tempC(245, 242, 40, 76)).toBeGreaterThan(17)      // real Black Sea coast pixel (18.7 °C)
    expect(tempC(245, 242, 40, 76)).toBeLessThan(20)
    expect(tempC(0, 0, 0, 0)).toBeNull()
  })

  it('paints a flat area as one band, more opaque than OWM, and never red', () => {
    const w = 4, data = new Uint8ClampedArray(w * w * 4)
    for (let i = 0; i < data.length; i += 4) data.set([255, 219, 40, 76], i)
    recolorTemp(data, w)
    const [r, g, b, a] = data.slice(0, 4)
    expect(a).toBeGreaterThan(76)
    expect(g).toBeGreaterThan(b)
    expect(r - g).toBeLessThan(120)   // amber at most, not red
    for (let i = 4; i < data.length; i += 4) expect([...data.slice(i, i + 4)]).toEqual([r, g, b, a])
  })

  it('draws a dark contour where the 2 °C band changes', () => {
    const w = 4, data = new Uint8ClampedArray(w * 1 * 4)
    // two columns at ~18 °C, two at ~22 °C: different bands
    data.set([245, 242, 40, 76], 0); data.set([245, 242, 40, 76], 4)
    data.set([255, 219, 40, 76], 8); data.set([255, 219, 40, 76], 12)
    expect(Math.floor(18.5 / TEMP_BAND_C)).not.toBe(Math.floor(22 / TEMP_BAND_C))
    recolorTemp(data, w)
    const lum = (i) => data[i] + data[i + 1] + data[i + 2]
    expect(lum(4)).toBeLessThan(lum(0) / 3)       // the pixel before the change is the contour
    expect(lum(12)).toBeGreaterThan(lum(4) * 3)
  })
})
