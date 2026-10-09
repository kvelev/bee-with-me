import api from './client'

// Auth
export const login = (username, password) => {
  const form = new URLSearchParams({ username, password })
  return api.post('/auth/login', form, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } })
}
export const getMe = () => api.get('/auth/me')

// Users
export const getUsers      = (params)   => api.get('/users/', { params })
export const importUsers   = (file)     => {
  const fd = new FormData(); fd.append('file', file)
  return api.post('/users/import', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
}
export const getUser       = (id)       => api.get(`/users/${id}`)
export const createUser    = (data)     => api.post('/users/', data)
export const updateUser    = (id, data) => api.put(`/users/${id}`, data)
export const deactivateUser = (id)      => api.patch(`/users/${id}/deactivate`)
export const reactivateUser = (id)      => api.patch(`/users/${id}/reactivate`)
export const deleteUser    = (id)       => api.delete(`/users/${id}`)

// Groups
export const getGroups            = (params) => api.get('/groups/', { params })
export const getGroupsWithMembers = (params) => api.get('/groups/', { params: { include_members: true, ...params } })
export const getGroup     = (id)            => api.get(`/groups/${id}`)
export const createGroup  = (data)          => api.post('/groups/', data)
export const updateGroup  = (id, data)      => api.put(`/groups/${id}`, data)
export const deleteGroup      = (id)            => api.delete(`/groups/${id}`)
export const deactivateGroup  = (id)            => api.patch(`/groups/${id}/deactivate`)
export const reactivateGroup  = (id)            => api.patch(`/groups/${id}/reactivate`)
export const addMember      = (gid, data)            => api.post(`/groups/${gid}/members`, data)
export const removeMember   = (gid, uid)             => api.delete(`/groups/${gid}/members/${uid}`)
export const setGroupLeader = (gid, uid, is_leader)  => api.post(`/groups/${gid}/members`, { user_id: uid, is_leader })

// Devices
export const getDevices    = ()             => api.get('/devices/')
export const createDevice  = (data)         => api.post('/devices/', data)
export const updateDevice  = (id, data)     => api.put(`/devices/${id}`, data)
export const assignDevice  = (id, userId)   => api.put(`/devices/${id}/assign`, { user_id: userId })
export const deleteDevice      = (id) => api.delete(`/devices/${id}`)
export const reactivateDevice  = (id) => api.post(`/devices/${id}/reactivate`)
export const permanentDeleteDevice = (id) => api.delete(`/devices/${id}/permanent`)

// Locations
export const getLivePositions = ()                 => api.get('/locations/live')
export const getOpenSOS       = ()                 => api.get('/locations/sos')
export const resolveSOS       = (id, notes)        => api.post(`/locations/sos/${id}/resolve`, null, { params: { notes } })
export const getHistory       = (deviceId, params) => api.get(`/locations/${deviceId}/history`, { params })
export const getTrail         = (minutes = 30)     => api.get('/locations/trail', { params: { minutes } })

// Serial
export const getSerialStatus = () => api.get('/serial/status')

// Tiles
export const startTileDownload = (password) => api.post('/tiles/bgmountains/download', { password })
export const getTileStatus      = () => api.get('/tiles/bgmountains/status')

// Export — returns raw blobs
export const exportCSV     = (params) => api.get('/export/csv',     { params, responseType: 'blob' })
export const exportGeoJSON = (params) => api.get('/export/geojson', { params, responseType: 'blob' })
export const exportPDF     = (params) => api.get('/export/pdf',     { params, responseType: 'blob' })

// Fire (EFFIS / GWIS)
export const getFireHotspots   = () => api.get('/fire/hotspots')
export const getFireBurntAreas = () => api.get('/fire/burnt-areas')
export const getFireStatus     = () => api.get('/fire/status')
// The backend defaults to 50 rows; every open alert must reach the banner, so ask for the maximum.
// Resolves with the array; `.total` (non-enumerable) is the server's X-Total-Count, so the banner
// can say when more alerts exist than were returned.
export const getFireAlerts = async (params) => {
  const res = await api.get('/fire/alerts', { params: { limit: 500, ...params }, fullResponse: true })
  const list = Array.isArray(res.data) ? res.data : []
  const total = Number.parseInt(res.headers?.['x-total-count'], 10)
  Object.defineProperty(list, 'total', { value: Number.isFinite(total) ? total : list.length })
  return list
}
export const acknowledgeFireAlert     = (id)  => api.post(`/fire/alerts/${id}/acknowledge`)
// Only the ids the operator could see: an alert that arrived meanwhile stays unacknowledged.
export const acknowledgeAllFireAlerts = (ids) => api.post('/fire/alerts/acknowledge-all', { alert_ids: ids })

// Settings (HQ + fire alarm)
export const getSettings  = ()     => api.get('/settings')
export const putSettings  = (body) => api.put('/settings', body)
export const putHQ        = (body) => api.put('/settings/hq', body)
export const putHQInitial = (body) => api.put('/settings/hq-initial', body)

// Weather: OpenWeatherMap through the backend, which holds the key (routers/weather.py)
export const getWeatherCurrent = (lat, lon)   => api.get('/weather/current', { params: { lat, lon } })
export const getWeatherBox     = (bbox, zoom) => api.get('/weather/box', { params: { bbox, zoom } })
export const getWeatherTile    = (src)        => api.get(src.replace(/^\/api/, ''), { responseType: 'blob' })

// Test mode (only when the server runs with ENABLE_TEST_ENDPOINTS=true; 404 otherwise)
export const getSimulation   = ()     => api.get('/test/simulation')
export const startSimulation = (body) => api.post('/test/simulation/start', body)
export const stopSimulation  = ()     => api.post('/test/simulation/stop')

// Fire: operator writes. Notes are free operator text; they travel only in these bodies.
export const dismissFireHotspot     = (id, notes) => api.post(`/fire/hotspots/${id}/dismiss`, { notes: notes ?? null })
export const createFieldReport      = (body)      => api.post('/fire/field-reports', body)
export const extinguishFieldReport  = (id)        => api.post(`/fire/field-reports/${id}/extinguish`)
export const getSuppressionZones    = (params)    => api.get('/fire/suppression-zones', { params })
export const createSuppressionZone  = (body)      => api.post('/fire/suppression-zones', body)
export const updateSuppressionZone  = (id, body)  => api.put(`/fire/suppression-zones/${id}`, body)
// Activation is explicit and carries the version the operator saw (B51/B52): a changed zone answers 409 zone_stale.
// A disabled zone is removed by the server 48 h later.
export const disableSuppressionZone = (id, expectedUpdatedAt) =>
  api.post(`/fire/suppression-zones/${id}/disable`, { expected_updated_at: expectedUpdatedAt })
export const enableSuppressionZone  = (id, expectedUpdatedAt) =>
  api.post(`/fire/suppression-zones/${id}/enable`, { expected_updated_at: expectedUpdatedAt })
