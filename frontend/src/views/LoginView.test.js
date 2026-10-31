import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

vi.mock('../api', () => ({ getMe: vi.fn(), login: vi.fn(), getFireAlerts: vi.fn().mockResolvedValue([]) }))

import { login, getMe } from '../api'
import { ApiError } from '../api/client'
import LoginView from './LoginView.vue'
import { i18n } from '../i18n/index.js'
import en from '../i18n/en.js'

async function mountView() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<i />' } },
      { path: '/map', component: { template: '<i />' } },
    ],
  })
  router.push('/')
  await router.isReady()
  const push = vi.spyOn(router, 'push')
  const w = mount(LoginView, { global: { plugins: [pinia, i18n, router] } })
  return { w, push }
}

async function submit(w, user, pass) {
  const inputs = w.findAll('form.login-card input')
  await inputs[0].setValue(user)
  await inputs[1].setValue(pass)
  await w.find('form.login-card').trigger('submit')
  await flushPromises()
}

describe('LoginView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    i18n.global.locale.value = 'en'
  })

  it('submits credentials and navigates to the map [T117]', async () => {
    login.mockResolvedValue({ access_token: 'at', refresh_token: 'rt' })
    getMe.mockResolvedValue({ role: 'admin', full_name: 'Admin' })
    const { w, push } = await mountView()
    await submit(w, 'admin', 'secret')
    expect(login).toHaveBeenCalledWith('admin', 'secret')
    expect(localStorage.getItem('token')).toBe('at')
    expect(push).toHaveBeenCalledWith('/map')
    expect(w.find('.error').exists()).toBe(false)
  })

  it('shows login.error on failure and keeps the form [T117]', async () => {
    login.mockRejectedValue(new ApiError('Not allowed', 403))
    const { w, push } = await mountView()
    await submit(w, 'admin', 'wrong')
    // the login form shows its own message, never the server's text
    expect(w.find('p.error').text()).toBe(en.login.error)
    expect(w.text()).not.toContain('Not allowed')
    expect(push).not.toHaveBeenCalled()
    const inputs = w.findAll('form.login-card input')
    expect(inputs[0].element.value).toBe('admin')
    expect(w.find('button[type=submit]').attributes('disabled')).toBeUndefined()
    expect(w.find('button[type=submit]').text()).toBe(en.login.submit)
  })
})
