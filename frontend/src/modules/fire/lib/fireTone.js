// The fire-alarm tone. Web Audio only, nothing fetched (TP-01).
//
// It must not be mistaken for the SOS alarm (SOSToast.vue: three fast, bright chirps, 880 to
// 1320 Hz, square-ish). The fire tone is two long, low, falling notes (a slow "wail"), once
// per ring: 740 Hz down to 520 Hz, then 520 Hz down to 370 Hz, triangle wave, about 1.3 s.
//
// Browsers keep an AudioContext suspended until the page has had a user gesture. That is never
// swallowed: `state` says 'blocked' so the banner can show it, and `unlock()` (called from a
// click or key press) resumes the context.

export const TONE_RUNNING     = 'running'
export const TONE_BLOCKED     = 'blocked'
export const TONE_UNSUPPORTED = 'unsupported'

export const WAIL = [
  { at: 0,    from: 740, to: 520, length: 0.55 },
  { at: 0.65, from: 520, to: 370, length: 0.65 },
]

let ctx = null

function context() {
  if (ctx) return ctx
  const Ctor = typeof window !== 'undefined' && (window.AudioContext || window.webkitAudioContext)
  if (!Ctor) return null
  try { ctx = new Ctor() } catch { ctx = null }
  return ctx
}

/** 'running' | 'blocked' | 'unsupported', as of right now. */
export function toneState() {
  const c = context()
  if (!c) return TONE_UNSUPPORTED
  return c.state === 'running' ? TONE_RUNNING : TONE_BLOCKED
}

function schedule(c) {
  const t0 = c.currentTime
  const out = c.createGain()
  out.connect(c.destination)
  for (const n of WAIL) {
    const osc = c.createOscillator()
    const env = c.createGain()
    osc.type = 'triangle'
    osc.frequency.setValueAtTime(n.from, t0 + n.at)
    osc.frequency.exponentialRampToValueAtTime(n.to, t0 + n.at + n.length)
    env.gain.setValueAtTime(0.0001, t0 + n.at)
    env.gain.exponentialRampToValueAtTime(0.3, t0 + n.at + 0.04)
    env.gain.setValueAtTime(0.3, t0 + n.at + n.length - 0.08)
    env.gain.exponentialRampToValueAtTime(0.0001, t0 + n.at + n.length)
    osc.connect(env)
    env.connect(out)
    osc.start(t0 + n.at)
    osc.stop(t0 + n.at + n.length + 0.02)
  }
}

/** Play the wail once. Returns the resulting state, so the caller can show 'blocked'. */
export function playFireTone() {
  const c = context()
  if (!c) return TONE_UNSUPPORTED
  if (c.state !== 'running') return TONE_BLOCKED   // no gesture yet; unlock() is the way out
  try {
    schedule(c)
    return TONE_RUNNING
  } catch {
    return TONE_UNSUPPORTED
  }
}

/** Call from a user gesture. Resolves to the state afterwards. */
export async function unlockFireTone() {
  const c = context()
  if (!c) return TONE_UNSUPPORTED
  try { await c.resume() } catch { /* still blocked: reported below */ }
  return c.state === 'running' ? TONE_RUNNING : TONE_BLOCKED
}
