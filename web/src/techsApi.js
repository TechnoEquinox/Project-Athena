// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { api } from './api'

export async function listTechs({ includeInactive = false } = {}) {
  return (await api.get(`/api/techs${includeInactive ? '?include_inactive=true' : ''}`)).techs
}

export async function createTech(data, { force = false } = {}) {
  return (await api.post('/api/admin/techs', force ? { ...data, force: true } : data)).tech
}

export async function updateTech(id, data) {
  return (await api.patch(`/api/admin/techs/${id}`, data)).tech
}

export async function deactivateTech(id) {
  const data = await api.delete(`/api/admin/techs/${id}`)
  return { tech: data.tech, loginDeactivated: data.login_deactivated }
}

export async function reactivateTech(id) {
  return (await api.post(`/api/admin/techs/${id}/reactivate`)).tech
}