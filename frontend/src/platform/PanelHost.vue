<script>
import { defineComponent, h, ref, createCommentVNode, watch, onErrorCaptured } from 'vue'

// Renderless boundary: one per panel. A panel that throws while rendering is logged once and renders nothing
// from then on; the neighbours stay. A panel with a retryKey function is tried again when retryKey(context) changes.
const PanelBoundary = defineComponent({
  name: 'PanelBoundary',
  props: {
    panel: { type: Object, required: true },
    context: { type: Object, default: undefined },
  },
  setup(props) {
    const failed = ref(false)

    onErrorCaptured((error) => {
      if (!failed.value) {
        failed.value = true
        console.error(`panel ${props.panel.id} failed`, error)
      }
      return false
    })

    watch(
      () => (typeof props.panel.retryKey === 'function' ? props.panel.retryKey(props.context) : undefined),
      (now, before) => { if (now !== before) failed.value = false },
    )

    return () => (failed.value ? null : h(props.panel.component, { context: props.context }))
  },
})

// Renders the panel list in order. Adds no element of its own.
export default defineComponent({
  name: 'PanelHost',
  props: {
    panels: { type: Array, default: () => [] },
    context: { type: Object, default: undefined },
  },
  setup(props) {
    return () => (props.panels.length ? props.panels.map((p) => h(PanelBoundary, { key: p.id, panel: p, context: props.context })) : createCommentVNode())
  },
})
</script>
