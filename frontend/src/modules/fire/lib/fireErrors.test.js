import { describe, it, expect } from 'vitest'
import { ApiError } from '../../../api/client'
import { fireErrorKey } from './fireErrors'

describe('fireErrorKey', () => {
  it('maps the 409 no_recent_position case [T19]', () => {
    expect(fireErrorKey(new ApiError('no_recent_position', 409))).toBe('fire.errors.noRecentPosition')
  })
  it('maps other statuses and a missing response [T19]', () => {
    expect(fireErrorKey(new ApiError('Hotspot not found', 404))).toBe('fire.errors.notFound')
    expect(fireErrorKey(new ApiError('Forbidden', 403))).toBe('fire.errors.forbidden')
    expect(fireErrorKey(new ApiError([{ msg: 'bad' }], 422))).toBe('fire.errors.invalid')
    expect(fireErrorKey(new ApiError('Network Error', undefined))).toBe('fire.errors.network')
    expect(fireErrorKey(new ApiError('Not Found', 404), 'report')).toBe('fire.errors.reportEndpoint')
    expect(fireErrorKey(new ApiError('boom', 500))).toBe('fire.errors.generic')
    expect(fireErrorKey(new ApiError('conflict', 409))).toBe('fire.errors.generic')
  })
  it('maps 409 zone_stale to its own message [B52]', () => {
    expect(fireErrorKey(new ApiError('zone_stale', 409))).toBe('fire.errors.zoneStale')
  })
})
