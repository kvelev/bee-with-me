import { describe, it, expect } from 'vitest'
import { compassFrom, downwindUnit, gridPoints, openMeteoUrl, parseOpenMeteo, nearestPoint } from './wind'

describe('wind helpers', () => {
  it('names the direction the wind comes from', () => {
    expect(compassFrom(0)).toBe('N')
    expect(compassFrom(353)).toBe('N')
    expect(compassFrom(72)).toBe('E')
    expect(compassFrom(225)).toBe('SW')
    expect(compassFrom(-90)).toBe('W')
    expect(compassFrom(null)).toBe('')
  })

  it('points the screen vector downwind: a northerly blows down the screen, a westerly to the right', () => {
    const north = downwindUnit(0)
    expect(north.x).toBeCloseTo(0)
    expect(north.y).toBeCloseTo(1)
    const west = downwindUnit(270)
    expect(west.x).toBeCloseTo(1)
    expect(west.y).toBeCloseTo(0)
  })

  it('spreads grid points over the box at cell centres', () => {
    const pts = gridPoints(20, 40, 30, 44, 5, 4)
    expect(pts).toHaveLength(20)
    expect(pts[0]).toEqual({ lat: 40.5, lon: 21 })
    expect(pts[19]).toEqual({ lat: 43.5, lon: 29 })
  })

  it('asks Open-Meteo for all points in one keyless request', () => {
    const url = openMeteoUrl([{ lat: 42.701, lon: 24.174 }, { lat: 42.5, lon: 23.3 }])
    expect(url).toContain('latitude=42.70,42.50&longitude=24.17,23.30')
    expect(url).toContain('wind_direction_10m')
    expect(url).toContain('wind_speed_unit=ms')
    expect(url).not.toMatch(/appid|apikey/i)
  })

  it('parses a multi-point and a single-point response, skipping unusable entries', () => {
    const loc = (lat, lon, speed, deg) => ({ latitude: lat, longitude: lon, current: { wind_speed_10m: speed, wind_direction_10m: deg, wind_gusts_10m: 6.5 } })
    const many = parseOpenMeteo([loc(42.69, 24.19, 2.42, 353), loc(42.5, 23.31, 2.21, 72), { latitude: 1, longitude: 2, current: {} }])
    expect(many).toHaveLength(2)
    expect(many[0]).toMatchObject({ lat: 42.69, lon: 24.19, speed: 2.42, deg: 353, gust: 6.5 })
    expect(many[1].vxNorm).toBeLessThan(0)   // from ENE: blows towards the west
    expect(parseOpenMeteo(loc(1, 2, 3, 90))).toHaveLength(1)
    expect(parseOpenMeteo(null)).toEqual([])
  })

  it('finds the nearest point', () => {
    const pts = [{ lat: 0, lon: 0 }, { lat: 10, lon: 10 }]
    expect(nearestPoint(pts, 9, 9)).toBe(pts[1])
    expect(nearestPoint([], 0, 0)).toBeNull()
  })
})
