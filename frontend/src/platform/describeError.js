// What a console line may say about an error: the message and the HTTP status, nothing else. An axios error carries
// the request config, and with it the bearer token, so the error object itself is never logged (B99, B108).
export function describeError(error) {
  const text = error?.message ?? String(error)
  const status = error?.response?.status
  return status ? `${text} (HTTP ${status})` : text
}
