<script>
import { defineComponent, h, ref, onErrorCaptured } from 'vue'

// Renderless boundary: one per banner. If the banner throws while rendering or updating, the error is
// logged once and this banner alone renders nothing from then on; its neighbours stay.
const BannerBoundary = defineComponent({
  name: 'BannerBoundary',
  props: { id: { type: String, required: true }, component: { type: [Object, Function], required: true } },
  setup(props) {
    const failed = ref(false)
    onErrorCaptured((error) => {
      if (!failed.value) {
        failed.value = true
        console.error(`banner ${props.id} failed`, error)
      }
      return false
    })
    return () => (failed.value ? null : h(props.component))
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
