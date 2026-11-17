// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { api } from './api'

const KINDS = ['clients', 'appointments', 'calls']

/** Deleted records still inside the retention window. kind: clients, appointments or calls. */
export async function listDeleted(kind) {
  if (!KINDS.includes(kind)) throw new Error(`Unknown kind: ${kind}`)
  const data = await api.get(`/api/admin/deleted-${kind}`)
  return { retentionDays: data.retention_days, items: data[`deleted_${kind}`] }
}

export function restoreClient(id, { force = false } = {}) {
  return api.post(`/api/admin/clients/${id}/restore`, force ? { force: true } : {})
}

export function restoreAppointment(id) {
  return api.post(`/api/admin/appointments/${id}/restore`)
}

export function restoreCall(id) {
  return api.post(`/api/admin/calls/${id}/restore`)
}