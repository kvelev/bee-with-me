<script>
import { defineComponent, h, ref, createCommentVNode, watch, onErrorCaptured } from 'vue'

// Renderless boundary: one per panel. A panel that throws any error captured from it (while rendering, but also
// from its own handlers and watchers) is logged once and renders nothing from then on; the neighbours stay. A panel with a retryKey function is tried again when retryKey(context) changes.
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

    let keyLogged = false
    const retryValue = () => {
      if (typeof props.panel.retryKey !== 'function') return undefined
      try {
        return props.panel.retryKey(props.context)
      } catch (error) {
        if (!keyLogged) {
          keyLogged = true
          console.error(`panel ${props.panel.id} retryKey failed`, error)
        }
        return undefined
      }
    }

    watch(
      retryValue,
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
