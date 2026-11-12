import { describeError } from './describeError.js'

// Global safety net for what no panel boundary catches. Without it the browser prints the raw error object, and an
// axios error carries the request config and with it the bearer token (B99, B108). Only the message and the HTTP
// status are ever logged. Nothing is shown on screen and no state changes.
const NO_DESCRIPTION = '[app] error (no description)'

function safeLine(build) {
  try {
    return build()
  } catch {
    return NO_DESCRIPTION
  }
}

export function installErrorHandlers(app, { target = window, log = console.error } = {}) {
  app.config.errorHandler = (error, _instance, info) => {
    log(safeLine(() => `[app] ${info}: ${describeError(error)}`))
  }

  const onRejection = (event) => {
    log(safeLine(() => `[app] unhandled rejection: ${describeError(event.reason)}`))
    try {
      event.preventDefault()
    } catch {
      // nothing to do: the line above is already logged
    }
  }
  // An error thrown outside Vue (a timer, an OpenLayers callback). A cross-origin script has no error object, only a
  // message (B147). Resource load errors do not bubble to the window, so this listener never sees them.
  const onError = (event) => {
    log(safeLine(() => `[app] uncaught error: ${describeError(event.error ?? event.message)}`))
    try {
      event.preventDefault()
    } catch {
      // nothing to do: the line above is already logged
    }
  }
  target.addEventListener('unhandledrejection', onRejection)
  target.addEventListener('error', onError)

  return () => {
    target.removeEventListener('unhandledrejection', onRejection)
    target.removeEventListener('error', onError)
  }
}
