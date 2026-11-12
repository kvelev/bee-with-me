import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getSerialStatus } from '../../api'

/** The state of the USB gateway as the backend reports it: `{ connected, port, frames_received }`, or `null`
 *  until the first answer. It is pushed by the `serial_status` message and fetched with the live channel. */
export const useGatewayStore = defineStore('gateway', () => {
  const status = ref(null)

  // An answer without a boolean `connected` (an empty `{}`, a null) is not a status: the pill keeps what it shows (B142).
  function applyStatus(data) {
    if (!data || typeof data !== 'object' || typeof data.connected !== 'boolean') return
    const { type, ...s } = data
    status.value = s
  }

  /** Never throws and never rejects: the port may be unconfigured, the session may have ended, the answer may be
   *  empty. The status stays as it was and the next resync tick asks again. */
  async function fetchStatus() {
    try {
      applyStatus(await getSerialStatus())
    } catch { /* port not configured, or no session yet: the next tick tries again */ }
  }

  return { status, applyStatus, fetchStatus }
})
