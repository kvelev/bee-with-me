import { describe, expect, it } from 'vitest'
import { describeError } from './describeError.js'

describe('describeError', () => {
  it('returns the message of an error without a response [B108]', () => {
    expect(describeError(new Error('boom'))).toBe('boom')
  })

  it('adds the HTTP status and nothing from the request config [B108]', () => {
    const error = Object.assign(new Error('Request failed'), { config: { headers: { Authorization: 'Bearer SECRET-TOKEN-B108' } }, response: { status: 500 } })
    const text = describeError(error)
    expect(text).toBe('Request failed (HTTP 500)')
    expect(text).not.toContain('SECRET-TOKEN-B108')
  })

  it('handles values that are not errors [B108]', () => {
    expect(describeError('plain')).toBe('plain')
    expect(describeError(undefined)).toBe('undefined')
    expect(describeError(null)).toBe('null')
    expect(describeError({ response: { status: 404 } })).toBe('[object Object] (HTTP 404)')
  })
})
