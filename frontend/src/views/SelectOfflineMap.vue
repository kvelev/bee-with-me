<template>
  <div class="page">

    <div class="page-header">
      <h2>{{ t('nav.selectofflinemap') }}</h2>
    </div>

    <div class="card offline-card">

      <div class="offline-description">
        <p>
          {{ t('selectOfflinemap.select') }}
        </p>
      </div>

      <!-- Зареждане -->
      <div
        v-if="loading"
        class="status"
      >
        {{ t('map.offlineMapsLoading') }}
      </div>

      <!-- Грешка -->
      <div
        v-else-if="error"
        class="error"
      >
        {{ error }}
      </div>

      <!-- Няма карти -->
      <div
        v-else-if="maps.length === 0"
        class="status"
      >
        {{ t('map.offlineMapsNoMaps') }}
      </div>

      <!-- Списък с карти -->
      <div
        v-else
        class="map-list"
      >
        <button
          v-for="map in maps"
          :key="map.id"
          type="button"
          class="map-item"
          :class="{ selected: selectedMap === map.id }"
          @click="selectedMap = map.id"
        >

          <span class="map-icon">
            🗺️
          </span>

          <span class="map-info">

            <span class="map-name">
              {{ map.name }}
            </span>

            <span class="map-file">
              {{ map.file }}
            </span>

          </span>

          <span
            v-if="selectedMap === map.id"
            class="map-check"
          >
            ✓
          </span>

        </button>
      </div>

      <!-- Бутони -->
      <div class="actions">

        <button
          type="button"
          class="secondary"
          @click="goBack"
          :disabled="selecting"
        >
          {{ t('common.cancel') }}
        </button>

        <button
          type="button"
          @click="loadMap"
          :disabled="!selectedMap || selecting"
        >
          {{
            selecting
              ? t('selectOfflinemap.loading')
              : t('selectOfflinemap.load')
          }}
        </button>

      </div>

    </div>

  </div>
</template>


<script setup>

import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'


const { t } = useI18n()
const router = useRouter()

const HOST = import.meta.env.VITE_TILE_HOST;
const PORT = import.meta.env.VITE_TILE_PORT;

const TILE_SERVER = `http://${HOST}:${PORT}`;


const maps = ref([])
const selectedMap = ref(null)

const loading = ref(false)
const selecting = ref(false)
const error = ref('')


/* --------------------------------------------------
 * Зареждане на списъка с MBTiles
 * -------------------------------------------------- */

async function loadMaps() {

  loading.value = true
  error.value = ''

  try {

    const response = await fetch(
      `${TILE_SERVER}/api/maps`
    )

    if (!response.ok) {
      throw new Error(
        `HTTP ${response.status}`
      )
    }

    const data = await response.json()

    maps.value = data.maps ?? []

    /*
     * Ако Node server вече има избрана карта,
     * маркираме я автоматично.
     */
    if (data.current) {
      selectedMap.value = data.current
    }

  } catch (e) {

    console.error(
      'Offline map server error:',
      e
    )

    maps.value = []

    error.value =
      t('map.offlineMapsServerError')

  } finally {

    loading.value = false

  }
}


/* --------------------------------------------------
 * Зареждане на избраната карта
 * -------------------------------------------------- */

async function loadMap() {

  if (!selectedMap.value || selecting.value) {
    return
  }

  selecting.value = true
  error.value = ''

  try {

    const response = await fetch(
      `${TILE_SERVER}/api/select/${encodeURIComponent(selectedMap.value)}`
    )

    if (!response.ok) {
      throw new Error(
        `HTTP ${response.status}`
      )
    }

    const data = await response.json()

    if (!data.success) {
      throw new Error(
        data.error ||
        'Map selection failed'
      )
    }


    /*
     * Запазваме избраната карта.
     *
     * MapView.vue ще я прочете при зареждане.
     */
    localStorage.setItem(
      'selectedOfflineMap',
      selectedMap.value
    )


    /*
     * Казваме коя карта е избрана.
     * Полезно е и ако по-късно решим да пазим
     * допълнителни данни за картата.
     */
    localStorage.setItem(
      'selectedOfflineMapName',
      data.map?.name ??
      selectedMap.value
    )

    window.dispatchEvent(new CustomEvent('offline-map-changed'))

    /*
     * Връщаме се към картата.
     */
    router.push('/map')

  } catch (e) {

    console.error(
      'Offline map selection error:',
      e
    )

    error.value =
      e.message ||
      t('map.offlineMapsSelectError')

  } finally {

    selecting.value = false

  }
}


/* --------------------------------------------------
 * Назад
 * -------------------------------------------------- */

function goBack() {
  router.back()
}


/* --------------------------------------------------
 * При отваряне на страницата
 * -------------------------------------------------- */

onMounted(() => {
  loadMaps()
})

</script>


<style scoped>

.page {
  padding: 24px;
  flex: 1;
}


/* --------------------------------------------------
 * Card
 * -------------------------------------------------- */

.offline-card {
  max-width: 760px;
  padding: 24px;
}


/* --------------------------------------------------
 * Description
 * -------------------------------------------------- */

.offline-description {
  margin-bottom: 18px;
}

.offline-description p {
  margin: 0;

  font-size: 14px;
  line-height: 1.6;

  color: var(--text-muted);
}


/* --------------------------------------------------
 * Status
 * -------------------------------------------------- */

.status {
  padding: 35px 20px;

  text-align: center;

  color: var(--text-muted);

  font-size: 13px;
}


/* --------------------------------------------------
 * Error
 * -------------------------------------------------- */

.error {
  margin: 16px 0;

  padding: 10px 12px;

  background: rgba(220, 38, 38, 0.12);

  border: 1px solid var(--danger);

  border-radius: 5px;

  color: var(--danger);

  font-size: 13px;
}


/* --------------------------------------------------
 * Map list
 * -------------------------------------------------- */

.map-list {
  max-height: 500px;

  overflow-y: auto;

  padding: 4px;

  border: 1px solid var(--border);

  border-radius: 6px;
}


/* --------------------------------------------------
 * Map item
 * -------------------------------------------------- */

.map-item {
  width: 100%;

  display: flex;
  align-items: center;

  gap: 12px;

  padding: 12px;

  margin-bottom: 4px;

  background: transparent;

  border: 1px solid transparent;

  border-radius: 5px;

  color: var(--text);

  text-align: left;

  cursor: pointer;

  transition:
    background 0.12s,
    border-color 0.12s;
}

.map-item:last-child {
  margin-bottom: 0;
}

.map-item:hover {
  background: var(--bg-card);

  border-color: var(--border);
}

.map-item.selected {
  background: var(--accent);

  border-color: var(--accent);

  color: #fff;
}


/* --------------------------------------------------
 * Icon
 * -------------------------------------------------- */

.map-icon {
  flex: 0 0 auto;

  font-size: 22px;
}


/* --------------------------------------------------
 * Information
 * -------------------------------------------------- */

.map-info {
  min-width: 0;

  display: flex;
  flex-direction: column;

  gap: 3px;
}

.map-name {
  overflow: hidden;

  white-space: nowrap;

  text-overflow: ellipsis;

  font-size: 14px;

  font-weight: 600;
}

.map-file {
  overflow: hidden;

  white-space: nowrap;

  text-overflow: ellipsis;

  font-size: 11px;

  color: var(--text-muted);
}

.map-item.selected .map-file {
  color: rgba(255, 255, 255, 0.75);
}


/* --------------------------------------------------
 * Check
 * -------------------------------------------------- */

.map-check {
  margin-left: auto;

  flex: 0 0 auto;

  font-size: 18px;

  font-weight: 700;
}


/* --------------------------------------------------
 * Actions
 * -------------------------------------------------- */

.actions {
  display: flex;

  justify-content: flex-end;

  gap: 8px;

  margin-top: 18px;
}

.actions button {
  min-width: 90px;
}

.actions .secondary {
  background: transparent;

  border: 1px solid var(--border);

  color: var(--text-muted);
}

.actions .secondary:hover {
  color: var(--text);

  border-color: var(--text-muted);
}

.actions button:disabled {
  opacity: 0.5;

  cursor: not-allowed;
}

</style>