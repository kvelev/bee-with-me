// Which message key a failed fire write shows. Callers read `.status` and `.detail` from the
// ApiError the client rejects with (see api/client.js); the text of an error is never shown or
// logged, because the request body may hold operator notes.
// `context` 'report': a 404 on filing a report means the backend lacks the endpoint, not a missing item.
export function fireErrorKey(err, context) {
  const detail = typeof err === 'string' ? err : err?.detail
  const status = typeof err === 'string' ? undefined : err?.status
  if (status === 409 && detail === 'no_recent_position') return 'fire.errors.noRecentPosition'
  if (status === 409 && detail === 'zone_stale') return 'fire.errors.zoneStale'
  if (status === 404 && context === 'report') return 'fire.errors.reportEndpoint'
  if (status === 404) return 'fire.errors.notFound'
  if (status === 403) return 'fire.errors.forbidden'
  if (status === 422) return 'fire.errors.invalid'
  if (status === undefined || status === 0) return 'fire.errors.network'
  return 'fire.errors.generic'
}
