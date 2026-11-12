import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getSerialStatus } from '../../api'

/** The state of the USB gateway as the backend reports it: `{ connected, port, frames_received }`, or `null`
 *  until the first answer. It is pushed by the `serial_status` message and fetched with the live channel. */
export const useGatewayStore = defineStore('gateway', () => {
  const status = ref(null)
  // Counts the applied pushes: a fetch that was sent before a push answers with older data and is dropped (B144).
  let pushes = 0

  // An answer without a boolean `connected` (an empty `{}`, a null) is not a status: the pill keeps what it shows (B142).
  function setStatus(data) {
    if (!data || typeof data !== 'object' || typeof data.connected !== 'boolean') return false
    const { type, ...s } = data
    status.value = s
    return true
  }

  /** A pushed `serial_status` message: always the newest state. */
  function applyStatus(data) {
    if (setStatus(data)) pushes += 1
  }

  /** Never throws and never rejects: the port may be unconfigured, the session may have ended, the answer may be
   *  empty. The status stays as it was and the next resync tick asks again. */
  async function fetchStatus() {
    const before = pushes
    try {
      const data = await getSerialStatus()
      if (pushes === before) setStatus(data)
    } catch { /* port not configured, or no session yet: the next tick tries again */ }
  }

  return { status, applyStatus, fetchStatus }
})
