import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'

vi.mock('../../../api', () => ({ getSerialStatus: vi.fn() }))

import { i18n } from '../../../i18n/index.js'
import { useGatewayStore } from '../store.js'
import GatewayStatus from './GatewayStatus.vue'
import en from '../i18n/en.js'
import bg from '../i18n/bg.js'

let pinia
const show = (props = {}) => mount(GatewayStatus, { props, global: { plugins: [pinia, i18n] } })

beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  i18n.global.locale.value = 'en'
})

describe('GatewayStatus', () => {
  it('shows connected with port and counter [T630]', () => {
    useGatewayStore().applyStatus({ connected: true, port: 'COM3', frames_received: 42 })
    const w = show()
    expect(w.get('.serial-status').classes()).toContain('serial-ok')
    expect(w.text()).toContain('Gateway connected')
    expect(w.text()).toContain('COM3')
    expect(w.text()).toContain('42 frames')
    w.unmount()
  })

  it('shows disconnected with the port [T630]', () => {
    useGatewayStore().applyStatus({ connected: false, port: 'COM3', frames_received: 42 })
    const w = show()
    expect(w.get('.serial-status').classes()).toContain('serial-off')
    expect(w.text()).toContain('Gateway disconnected')
    expect(w.text()).toContain('COM3')
    expect(w.text()).not.toContain('frames')
    w.unmount()
  })

  it('renders nothing without a status [T630]', () => {
    const w = show()
    expect(w.find('.serial-status').exists()).toBe(false)
    w.unmount()
  })

  it('the root element carries no context attribute [T630]', () => {
    useGatewayStore().applyStatus({ connected: true, port: 'COM3', frames_received: 1 })
    const w = show({ context: { anything: true } })
    expect(w.get('.serial-status').attributes('context')).toBeUndefined()
    w.unmount()
  })

  it('the frames word comes from i18n in both languages and a missing port leaves no dangling separator [B141]', () => {
    expect(en.gateway.frames).toContain('{n}')
    expect(bg.gateway.frames).toContain('{n}')
    useGatewayStore().applyStatus({ connected: true, frames_received: 7 })
    const w = show()
    expect(w.text()).toContain('7 frames')
    expect(w.text()).not.toMatch(/·\s*·/)
    i18n.global.locale.value = 'bg'
    return w.vm.$nextTick().then(() => {
      expect(w.text()).toContain('7 кадъра')
      w.unmount()
    })
  })
})
