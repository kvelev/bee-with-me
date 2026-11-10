<script>
import { defineComponent, h, ref, watch, onErrorCaptured, onBeforeUnmount } from 'vue'

const RETRY_MS = 5000

// Renderless boundary: one per banner. A banner that throws while rendering or updating is replaced by Vue's
// own empty comment node (no extra element), the error is logged, and the neighbours stay.
// The banner is NOT latched off. It heals in three ways:
//  1. its own reactive data changes (Vue keeps the failed instance mounted and tracked, so it re-renders itself),
//  2. its component/id changes (new key, remount),
//  3. a retry remount every RETRY_MS after a failure, which also covers errors that never touch reactive data.
// Logging is deduplicated: the same error (message) is logged at most once per RETRY_MS, a different error at once.
// SOS goes through exactly the same path, so it is never disabled either; it is simply retried on every update.
const BannerBoundary = defineComponent({
  name: 'BannerBoundary',
  props: { id: { type: String, required: true }, component: { type: [Object, Function], required: true } },
  setup(props) {
    const attempt = ref(0)
    let lastKey = null
    let lastAt = 0
    let timer = null

    const scheduleRetry = () => {
      if (timer !== null) return
      timer = setTimeout(() => {
        timer = null
        attempt.value += 1
      }, RETRY_MS)
    }

    onErrorCaptured((error) => {
      const key = String(error && error.message ? error.message : error)
      const now = Date.now()
      if (key !== lastKey || now - lastAt >= RETRY_MS) {
        lastKey = key
        lastAt = now
        console.error(`banner ${props.id} failed`, error)
      }
      scheduleRetry()
      return false
    })

    watch(() => [props.id, props.component], () => { lastKey = null })
    onBeforeUnmount(() => {
      if (timer !== null) clearTimeout(timer)
      timer = null
    })

    return () => h(props.component, { key: attempt.value })
  },
})

// Renders the sorted banner list in order. Adds no element of its own: the DOM under <main class="main-content">
// is the banners' own markup.
export default defineComponent({
  name: 'BannerStack',
  props: { banners: { type: Array, default: () => [] } },
  setup(props) {
    return () => props.banners.map((b) => h(BannerBoundary, { key: b.id, id: b.id, component: b.component }))
  },
})
</script>
