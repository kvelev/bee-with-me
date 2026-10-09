import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../api', () => ({ getTileStatus: vi.fn() }))

// useSettings keeps module state (one choice per browser): load a fresh copy per test
async function fresh(stored) {
  vi.resetModules()
  localStorage.clear()
  if (stored !== undefined) localStorage.setItem('bgMountainsOffline', stored)
  const api = await import('../api')
  const mod = await import('./useSettings')
  return { api, ...mod.useSettings() }
}

describe('BG Mountains online/offline default', () => {
  beforeEach(() => vi.clearAllMocks())

  it('uses offline tiles when nobody chose and the server has them', async () => {
    const s = await fresh()
    s.api.getTileStatus.mockResolvedValue({ available: true })
    await s.resolveBgMountainsDefault()
    expect(s.bgMountainsOffline.value).toBe(true)
    expect(localStorage.getItem('bgMountainsOffline')).toBeNull()   // a default, not a stored choice
  })

  it('uses online tiles when nobody chose and the server has none', async () => {
    const s = await fresh()
    s.api.getTileStatus.mockResolvedValue({ available: false })
    await s.resolveBgMountainsDefault()
    expect(s.bgMountainsOffline.value).toBe(false)
  })

  it('never overrides a stored choice', async () => {
    const s = await fresh('true')
    s.api.getTileStatus.mockResolvedValue({ available: false })
    await s.resolveBgMountainsDefault()
    expect(s.bgMountainsOffline.value).toBe(true)
    expect(s.api.getTileStatus).not.toHaveBeenCalled()
  })

  it('retries later when the status cannot be read yet (not logged in)', async () => {
    const s = await fresh()
    s.api.getTileStatus.mockRejectedValueOnce({ status: 401 }).mockResolvedValue({ available: true })
    await s.resolveBgMountainsDefault()
    expect(s.bgMountainsOffline.value).toBe(false)
    await s.resolveBgMountainsDefault()
    expect(s.bgMountainsOffline.value).toBe(true)
  })

  it('an explicit choice is stored and wins over a late default', async () => {
    const s = await fresh()
    let answer
    s.api.getTileStatus.mockReturnValue(new Promise(r => { answer = r }))
    const pending = s.resolveBgMountainsDefault()
    s.setBgMountainsOffline(false)
    answer({ available: true })
    await pending
    expect(s.bgMountainsOffline.value).toBe(false)
    expect(localStorage.getItem('bgMountainsOffline')).toBe('false')
  })
})
