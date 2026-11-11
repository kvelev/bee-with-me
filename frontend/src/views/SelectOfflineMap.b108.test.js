import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { i18n } from '../i18n/index.js'
import SelectOfflineMap from './SelectOfflineMap.vue'

const axiosLike = () => Object.assign(new Error('Request failed'), { config: { headers: { Authorization: 'Bearer SECRET-TOKEN-B108' } }, response: { status: 500 } })
const okJson = (body) => ({ ok: true, json: async () => body })

function mountView() {
  return mount(SelectOfflineMap, { global: { plugins: [i18n], mocks: { $router: {} }, stubs: {} } })
}

function expectSafe(err) {
  expect(err).toHaveBeenCalled()
  const args = err.mock.calls.flat()
  expect(args.some((a) => a !== null && typeof a === 'object')).toBe(false)
  const text = args.join(' ')
  expect(text).not.toContain('SECRET-TOKEN-B108')
  expect(text).toContain('Request failed')
  expect(text).toContain('HTTP 500')
}

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn(), back: vi.fn() }) }))

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('SelectOfflineMap logs carry the message and status, never the error object [B108]', () => {
  it('loading the map list fails [B108]', async () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.stubGlobal('fetch', vi.fn(async () => { throw axiosLike() }))
    mountView()
    await flushPromises()
    expectSafe(err)
  })

  it('selecting a map fails [B108]', async () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    const fetchMock = vi.fn(async (url) => {
      if (String(url).includes('/api/select/')) throw axiosLike()
      return okJson({ maps: [{ id: 'm1', name: 'Rila', file: 'rila.mbtiles' }] })
    })
    vi.stubGlobal('fetch', fetchMock)
    const w = mountView()
    await flushPromises()
    await w.get('.map-item').trigger('click')
    await w.findAll('.actions button')[1].trigger('click')
    await flushPromises()
    expectSafe(err)
  })
})
