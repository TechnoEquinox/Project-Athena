// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { api, qs } from './api'

const BASE = '/api/admin/server'

export const getHealth = () => api.get(`${BASE}/health`)

export const getHistory = (hours = 24) => api.get(`${BASE}/history${qs({ hours })}`)

export async function getUpdates() {
  const data = await api.get(`${BASE}/updates`)
  return data.updates
}

export async function getBackups() {
  const data = await api.get(`${BASE}/backups`)
  return data.backups
}

export const listJobs = () => api.get(`${BASE}/jobs`)

export const getJob = (id) => api.get(`${BASE}/jobs/${encodeURIComponent(id)}`)

/**
 * Ask the server to do something. `check` holds the password and 2FA code for the
 * actions that need them: { current_password, code } or { current_password, recovery_code }.
 */
export function requestJob(action, check = {}) {
  return api.post(`${BASE}/jobs`, { action, ...check })
}
