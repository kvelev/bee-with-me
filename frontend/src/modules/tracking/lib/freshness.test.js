import { describe, it, expect } from 'vitest'
import {
  ageMs, contactAt, formatAge, freshnessOf, byUrgency,
  LIVE, STALE, LOST, STALE_MS, LOST_MS,
} from './freshness'

const NOW = new Date('2026-09-08T12:00:00Z').getTime()
const agoMs = (ms) => new Date(NOW - ms).toISOString()

describe('contactAt', () => {
  it('prefers received_at (server clock) over recorded_at (device clock)', () => {
    const pos = {
      received_at: '2026-09-08T12:00:00Z',
      recorded_at: '2020-01-01T00:00:00Z',   // device clock badly skewed
    }
    expect(contactAt(pos)).toBe(new Date('2026-09-08T12:00:00Z').getTime())
  })

  it('falls back to recorded_at for rows written before received_at was carried through', () => {
    expect(contactAt({ recorded_at: '2026-09-08T11:00:00Z' }))
      .toBe(new Date('2026-09-08T11:00:00Z').getTime())
  })

  it('returns null when there is no usable timestamp', () => {
    expect(contactAt({})).toBeNull()
    expect(contactAt({ received_at: 'not-a-date' })).toBeNull()
    expect(contactAt(null)).toBeNull()
  })
})

describe('freshnessOf', () => {
  it('is live just inside the stale threshold', () => {
    expect(freshnessOf({ received_at: agoMs(STALE_MS - 1000) }, NOW)).toBe(LIVE)
  })

  it('is stale just past 10 minutes', () => {
    expect(freshnessOf({ received_at: agoMs(STALE_MS + 1000) }, NOW)).toBe(STALE)
  })

  it('is lost past 30 minutes', () => {
    expect(freshnessOf({ received_at: agoMs(LOST_MS + 1000) }, NOW)).toBe(LOST)
  })

  it('a device with a fast clock does not get to look fresh', () => {
    // recorded_at is in the future, received_at is an hour old — the server clock wins
    const pos = { recorded_at: new Date(NOW + 3_600_000).toISOString(), received_at: agoMs(3_600_000) }
    expect(freshnessOf(pos, NOW)).toBe(LOST)
  })
})

describe('ageMs', () => {
  it('never reports a negative age', () => {
    const pos = { received_at: new Date(NOW + 60_000).toISOString() }
    expect(ageMs(pos, NOW)).toBe(0)
  })
})

describe('formatAge', () => {
  it('formats across the units the panel uses', () => {
    expect(formatAge(0)).toBe('0s')
    expect(formatAge(42_000)).toBe('42s')
    expect(formatAge(7 * 60_000)).toBe('7m')
    expect(formatAge(64 * 60_000)).toBe('1h04')
    expect(formatAge(50 * 3_600_000)).toBe('2d')
    expect(formatAge(null)).toBe('—')
  })
})

describe('byUrgency', () => {
  it('puts SOS above everything, however fresh', () => {
    const sos   = { sos_active: true,  received_at: agoMs(1000) }
    const stale = { sos_active: false, received_at: agoMs(LOST_MS * 2) }
    expect([stale, sos].sort((a, b) => byUrgency(a, b, NOW))[0]).toBe(sos)
  })

  it('orders the rest oldest-contact first', () => {
    const fresh  = { received_at: agoMs(1000) }
    const stale  = { received_at: agoMs(STALE_MS + 1000) }
    const lost   = { received_at: agoMs(LOST_MS + 1000) }
    const sorted = [fresh, lost, stale].sort((a, b) => byUrgency(a, b, NOW))
    expect(sorted).toEqual([lost, stale, fresh])
  })
})
