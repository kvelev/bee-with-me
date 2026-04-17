import api from './client'

// Auth
export const login = (username, password) => {
  const form = new URLSearchParams({ username, password })
  return api.post('/auth/login', form, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } })
}
export const getMe = () => api.get('/auth/me')

// Users
export const getUsers      = ()         => api.get('/users/')
export const getUser       = (id)       => api.get(`/users/${id}`)
export const createUser    = (data)     => api.post('/users/', data)
export const updateUser    = (id, data) => api.put(`/users/${id}`, data)
export const deactivateUser = (id)      => api.patch(`/users/${id}/deactivate`)
export const reactivateUser = (id)      => api.patch(`/users/${id}/reactivate`)
export const deleteUser    = (id)       => api.delete(`/users/${id}`)

// Groups
export const getGroups    = ()              => api.get('/groups/')
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
export const deleteDevice  = (id)           => api.delete(`/devices/${id}`)

// Locations
export const getLivePositions = ()                 => api.get('/locations/live')
export const getOpenSOS       = ()                 => api.get('/locations/sos')
export const resolveSOS       = (id, notes)        => api.post(`/locations/sos/${id}/resolve`, null, { params: { notes } })
export const getHistory       = (deviceId, params) => api.get(`/locations/${deviceId}/history`, { params })
export const getTrail         = (minutes = 30)     => api.get('/locations/trail', { params: { minutes } })

// Export — returns raw blobs
export const exportCSV     = (params) => api.get('/export/csv',     { params, responseType: 'blob' })
export const exportGeoJSON = (params) => api.get('/export/geojson', { params, responseType: 'blob' })
export const exportPDF     = (params) => api.get('/export/pdf',     { params, responseType: 'blob' })
