<template>
  <div class="page">
    <div class="page-header"><h2>{{ t('export.title') }}</h2></div>

    <div class="card">
      <h3 class="section-title">{{ t('export.filters') }}</h3>
      <div class="filter-grid">
        <div class="form-group">
          <label>{{ t('export.from') }}</label>
          <input v-model="filters.from" type="datetime-local" />
        </div>
        <div class="form-group">
          <label>{{ t('export.to') }}</label>
          <input v-model="filters.to" type="datetime-local" />
        </div>
        <div class="form-group">
          <label>{{ t('export.group') }}</label>
          <select v-model="filters.group_id">
            <option :value="undefined">{{ t('export.allGroups') }}</option>
            <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}</option>
          </select>
        </div>
        <div class="form-group">
          <label>{{ t('export.person') }}</label>
          <select v-model="filters.user_id">
            <option :value="undefined">{{ t('export.allPersons') }}</option>
            <option v-for="u in users" :key="u.id" :value="u.id">{{ u.full_name }}</option>
          </select>
        </div>
      </div>

      <div class="export-btns">
        <button @click="doExport('csv')"     :disabled="loading">
          {{ loading === 'csv'     ? t('export.generating') : t('export.csv') }}
        </button>
        <button @click="doExport('geojson')" :disabled="loading">
          {{ loading === 'geojson' ? t('export.generating') : t('export.geojson') }}
        </button>
        <button @click="doExport('pdf')"     :disabled="loading">
          {{ loading === 'pdf'     ? t('export.generating') : t('export.pdf') }}
        </button>
      </div>

      <p v-if="error" class="error">{{ error }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { getGroups, getUsers, exportCSV, exportGeoJSON, exportPDF } from '../api'

const { t } = useI18n()
const groups  = ref([])
const users   = ref([])
const loading = ref(false)
const error   = ref('')
const filters = ref({ from: undefined, to: undefined, group_id: undefined, user_id: undefined })

onMounted(async () => {
  const [gr, ur] = await Promise.all([getGroups(), getUsers({ limit: 500 })])
  groups.value = gr.items
  users.value  = ur.items
})

const exportFns = { csv: exportCSV, geojson: exportGeoJSON, pdf: exportPDF }
const mimeTypes = { csv: 'text/csv', geojson: 'application/geo+json', pdf: 'application/pdf' }

async function doExport(type) {
  error.value   = ''
  loading.value = type
  try {
    const params = Object.fromEntries(
      Object.entries(filters.value).filter(([, v]) => v !== undefined && v !== ''),
    )
    const blob = await exportFns[type](params)
    const url  = URL.createObjectURL(new Blob([blob], { type: mimeTypes[type] }))
    const a    = Object.assign(document.createElement('a'), {
      href: url,
      download: `locations.${type === 'geojson' ? 'geojson' : type}`,
    })
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    error.value = typeof e === 'string' ? e : 'Export failed'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.page         { padding: 24px; flex: 1; }
.section-title{ font-size: 14px; font-weight: 600; margin-bottom: 16px; color: var(--text-muted); }
.filter-grid  { display: grid; grid-template-columns: 1fr 1fr; gap: 0 20px; }
.export-btns  { display: flex; gap: 12px; margin-top: 24px; flex-wrap: wrap; }
.error        { color: var(--danger); font-size: 13px; margin-top: 12px; }
</style>
