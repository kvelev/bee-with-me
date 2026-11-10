import { describe, it, expect } from 'vitest'
import { alarmsTurnedOff, kmError, wholeError, kmToM, mToKm, LIMITS } from './settingsForm'

const on = { is_hq_alarm_enabled: true, is_rescuer_alarm_enabled: true }

describe('settingsForm', () => {
  it('asks for confirmation only when an alarm goes from on to off [T13]', () => {
    expect(alarmsTurnedOff(on, on)).toEqual([])
    expect(alarmsTurnedOff(on, { ...on, is_hq_alarm_enabled: false })).toEqual(['hq'])
    expect(alarmsTurnedOff(on, { is_hq_alarm_enabled: false, is_rescuer_alarm_enabled: false })).toEqual(['hq', 'rescuer'])
  })

  it('an alarm that was already off needs no confirmation [T13]', () => {
    const cur = { is_hq_alarm_enabled: false, is_rescuer_alarm_enabled: true }
    expect(alarmsTurnedOff(cur, cur)).toEqual([])
    expect(alarmsTurnedOff(cur, { ...cur, is_hq_alarm_enabled: true })).toEqual([])
  })

  it('validates km range and rejects empty or text [T13]', () => {
    expect(kmError(0.1)).toBeNull()
    expect(kmError('100')).toBeNull()
    expect(kmError(0.05)).toBe('errRangeKm')
    expect(kmError(100.1)).toBe('errRangeKm')
    expect(kmError('')).toBe('errRangeKm')
    expect(kmError('abc')).toBe('errRangeKm')
  })

  it('validates whole numbers in range [T13]', () => {
    expect(wholeError(24, LIMITS.hours, 'e')).toBeNull()
    expect(wholeError(1.5, LIMITS.hours, 'e')).toBe('e')
    expect(wholeError(169, LIMITS.hours, 'e')).toBe('e')
    expect(wholeError(0, LIMITS.minutes, 'e')).toBe('e')
  })

  it('converts km and metres without float drift [T13]', () => {
    expect(kmToM(0.3)).toBe(300)
    expect(kmToM('10')).toBe(10000)
    expect(mToKm(3000)).toBe(3)
  })
})
