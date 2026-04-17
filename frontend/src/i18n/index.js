import { createI18n } from 'vue-i18n'
import en from './en'
import bg from './bg'

const saved = localStorage.getItem('locale') || 'en'

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
  localStorage.setItem('locale', code)
}
