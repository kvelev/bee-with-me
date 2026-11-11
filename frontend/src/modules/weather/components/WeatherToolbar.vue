<template>
  <template v-if="context.activeBasemap.value === 'satellite' || context.activeBasemap.value === 'offline'">
    <span class="bm-row-break" />
    <button
      v-for="wl in WEATHER_LAYERS" :key="wl.id"
      :class="['bm-btn', 'bm-btn-weather', { active: weatherUi.layerId === wl.id }]"
      @click="weatherUi.toggle(wl.id)"
    >{{ t(`map.weather.${wl.id}`) }}</button>
  </template>
</template>

<script setup>
// The four weather buttons of the map toolbar, on their own row, shown on the satellite and offline basemaps.
// A fragment (no wrapper), so the buttons stay direct flex children of the toolbar. The overlay itself is
// switched on by WeatherPanel, which reacts to useWeatherUi().layerId.
import { useI18n } from 'vue-i18n'
import { WEATHER_LAYERS } from '../layers.js'
import { useWeatherUi } from '../ui.js'

defineProps({ context: { type: Object, required: true } })

const { t } = useI18n()
const weatherUi = useWeatherUi()
</script>

<style scoped>
/* Same rules as MapView's .bm-btn, .bm-btn-weather and .bm-row-break (scoped CSS does not reach a child component). */
.bm-btn {
  background: var(--bg-panel); border: 1px solid var(--border);
  color: var(--text-muted); padding: 5px 10px; font-size: 12px; border-radius: 4px;
}
.bm-btn:hover  { color: var(--text); }
.bm-btn.active { background: var(--accent); border-color: var(--accent); color: #fff; }
.bm-btn-weather.active { background: #0369a1; border-color: #0369a1; }
.bm-row-break { flex-basis: 100%; height: 0; }
</style>
