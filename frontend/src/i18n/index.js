import { createI18n } from 'vue-i18n'
import en from './en'
import bg from './bg'

// Runs at import time, so an unguarded throw here white-screens the whole app before it
// renders. localStorage is unavailable or throws in private windows and with site data
// blocked — falling back to English is always better than not booting.
function savedLocale() {
  try {
    return localStorage.getItem('locale') || 'en'
  } catch {
    return 'en'
  }
}

const saved = savedLocale()

export const i18n = createI18n({
  legacy: false,
  locale: saved,
  fallbackLocale: 'en',
  messages: { en, bg },
})

export const LOCALES = [
  { code: 'en', label: 'EN' },
  { code: 'bg', label: 'БГ' },
]

export function setLocale(code) {
  i18n.global.locale.value = code
  try {
    localStorage.setItem('locale', code)
  } catch { /* not persisted this session — the switch itself still works */ }
}
