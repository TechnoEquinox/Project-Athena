// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { api } from './api'

export async function listLocations({ includeInactive = false } = {}) {
  return (await api.get(`/api/locations${includeInactive ? '?include_inactive=true' : ''}`)).locations
}

export async function createLocation(name) {
  return (await api.post('/api/admin/locations', { name })).location
}

export async function renameLocation(id, name) {
  return (await api.patch(`/api/admin/locations/${id}`, { name })).location
}

export async function deactivateLocation(id) {
  return (await api.delete(`/api/admin/locations/${id}`)).location
}

export async function reactivateLocation(id) {
  return (await api.post(`/api/admin/locations/${id}/reactivate`)).location
}