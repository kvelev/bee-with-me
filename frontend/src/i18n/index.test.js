import { describe, it, expect, beforeEach } from 'vitest'
import { i18n, setLocale } from './index'

describe('i18n', () => {
  beforeEach(() => {
    setLocale('en')
    localStorage.clear()
  })

  it('default locale is en or bg (from localStorage)', () => {
    const locale = i18n.global.locale.value
    expect(['en', 'bg']).toContain(locale)
  })

  it('setLocale switches to bg', () => {
    setLocale('bg')
    expect(i18n.global.locale.value).toBe('bg')
  })

  it('setLocale persists to localStorage', () => {
    setLocale('bg')
    expect(localStorage.getItem('locale')).toBe('bg')
  })

  it('setLocale back to en', () => {
    setLocale('bg')
    setLocale('en')
    expect(i18n.global.locale.value).toBe('en')
  })

  it('en has nav.map key', () => {
    setLocale('en')
    expect(i18n.global.t('nav.map')).toBeTruthy()
  })

  it('bg has nav.map key', () => {
    setLocale('bg')
    expect(i18n.global.t('nav.map')).toBeTruthy()
  })

  it('en and bg nav.map keys differ', () => {
    setLocale('en')
    const en = i18n.global.t('nav.map')
    setLocale('bg')
    const bg = i18n.global.t('nav.map')
    expect(en).not.toBe(bg)
  })
})
