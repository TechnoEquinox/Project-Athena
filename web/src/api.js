// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

let csrfToken = null
let onUnauthorized = () => {}

export function setCsrf(token) {
  csrfToken = token
}

export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn
}

export class ApiError extends Error {
  constructor(status, body) {
    const data = body || {}
    super(data.message || data.error || `Request failed (${status})`)
    this.status = status
    this.body = data
    this.code = data.error
  }
}

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])
// A 401 from these means "wrong credentials" or "not signed in yet", not "session expired"
const QUIET_401 = ['/api/auth/login', '/api/auth/me']

export async function request(method, path, body) {
  const headers = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (!SAFE_METHODS.has(method) && csrfToken) headers['X-CSRF-Token'] = csrfToken

  let response
  try {
    response = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: 'same-origin',
    })
  } catch {
    throw new ApiError(0, { error: 'network', message: 'Cannot reach the server.' })
  }

  let data = null
  try {
    data = await response.json()
  } catch {
    data = null
  }

  if (!response.ok) {
    const error = new ApiError(response.status, data)
    if (response.status === 401 && !QUIET_401.some((p) => path.startsWith(p))) {
      onUnauthorized(error)
    }
    throw error
  }
  return data
}

/** Fetch a file (CSV). Cookies go along, and a 401 error is handled like any other request. */
export async function download(path) {
  let response
  try {
    response = await fetch(path, { credentials: 'same-origin' })
  } catch {
    throw new ApiError(0, { error: 'network', message: 'Cannot reach the server.' })
  }
  if (!response.ok) {
    let data = null
    try {
      data = await response.json()
    } catch {
      data = null
    }
    const error = new ApiError(response.status, data)
    if (response.status === 401) onUnauthorized(error)
    throw error
  }
  return { blob: await response.blob(), filename: filenameFrom(response.headers.get('Content-Disposition')) }
}

export function filenameFrom(header) {
  const match = /filename="([^"]+)"/.exec(header ?? '')
  return match ? match[1] : null
}

export const api = {
  get: (path) => request('GET', path),
  post: (path, body = {}) => request('POST', path, body),
  patch: (path, body) => request('PATCH', path, body),
  put: (path, body) => request('PUT', path, body),
  delete: (path) => request('DELETE', path),
}

export function qs(params = {}) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.append(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}