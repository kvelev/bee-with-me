// State of the tracker panel that the map view shares with the panel: the mode, the rank filter, the selected device
// and the list both the panel and the map draw. No OpenLayers here (rule `manifest-reaches-no-openlayers`).
// The 10 second tick lives here, not in the panel: the order of the list and the marker styles depend on it, so the map
// view starts and stops it and a panel that is not mounted does not freeze the order.
import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { byUrgency } from './lib/freshness.js'
import { useTrackingStore } from './store.js'

const TICK_MS = 10_000

export const useTrackerUi = defineStore('trackerUi', () => {
  const tracking = useTrackingStore()

  const viewMode = ref('individuals')   // 'individuals' | 'groups'
  const rankFilter = ref('')
  const selectedDeviceId = ref(null)
  // id -> { id, name, color, members: [{id, full_name, rank, is_leader}] }; set by the view, which loads the teams.
  const groupsMap = ref({})

  // Drives every relative age and the urgency order. Without it the ages would only refresh when some other device
  // happens to report, so a panel full of silent trackers would freeze its own clock, exactly when the ages matter most.
  const nowTick = ref(Date.now())
  let timer = null

  const rankFiltered = computed(() => {
    const q = rankFilter.value.trim().toLowerCase()
    const list = !q
      ? tracking.positionList
      : tracking.positionList.filter((pos) => pos.rank?.toLowerCase().includes(q))
    // Worst-first: SOS, then longest out of contact. What needs attention surfaces itself.
    return [...list].sort((a, b) => byUrgency(a, b, nowTick.value))
  })

  // In teams mode show only leaders, labelled by team name.
  const displayList = computed(() => {
    if (viewMode.value === 'individuals') return rankFiltered.value
    return rankFiltered.value
      .filter((pos) => pos.groups?.some((g) => g.is_leader))
      .map((pos) => {
        const leaderGroup = pos.groups.find((g) => g.is_leader)
        return { ...pos, displayLabel: leaderGroup?.name ?? pos.full_name }
      })
  })

  // The groups with their leader's live position, for the teams view of the panel.
  const groupsWithLeaders = computed(() => {
    const byGroup = {}
    for (const pos of rankFiltered.value) {
      for (const g of (pos.groups ?? [])) {
        if (!byGroup[g.id]) byGroup[g.id] = { id: g.id, name: g.name, color: g.color, leader: null }
        if (g.is_leader) byGroup[g.id].leader = pos
      }
    }
    return Object.values(byGroup).sort((a, b) => a.name.localeCompare(b.name))
  })

  // A volunteer who left the list cannot stay selected.
  watch(displayList, (list) => {
    if (selectedDeviceId.value && !list.some((p) => p.device_id === selectedDeviceId.value)) selectedDeviceId.value = null
  })

  function select(deviceId) { selectedDeviceId.value = deviceId ?? null }

  // Idempotent: the view calls it after several awaits.
  function startTick() {
    if (timer !== null) return
    timer = setInterval(() => { nowTick.value = Date.now() }, TICK_MS)
  }
  function stopTick() {
    clearInterval(timer)
    timer = null
  }

  // The map starts fresh on every visit.
  function reset() {
    viewMode.value = 'individuals'
    rankFilter.value = ''
    selectedDeviceId.value = null
    groupsMap.value = {}
    nowTick.value = Date.now()      // the tick was stopped while away: ages start current, not up to 10 s old (B129)
  }

  return {
    viewMode, rankFilter, selectedDeviceId, groupsMap, nowTick,
    displayList, groupsWithLeaders,
    select, startTick, stopTick, reset,
  }
})
