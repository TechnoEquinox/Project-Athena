// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { api, qs } from './api'

const base = '/api/calls'

export async function listStatuses() {
  return (await api.get(`${base}/statuses`)).statuses
}

export function listCalls({
  open, status, tech_id, client_id, unlinked, from, to, order, limit, offset,
} = {}) {
  return api.get(
    `${base}${qs({ open, status, tech_id, client_id, unlinked, from, to, order, limit, offset })}`,
  )
}

export async function getCall(id) {
  return (await api.get(`${base}/${id}`)).call
}

export async function createCall(data) {
  return (await api.post(base, data)).call
}

export async function updateCall(id, data) {
  return (await api.patch(`${base}/${id}`, data)).call
}

export async function deleteCall(id) {
  await api.delete(`${base}/${id}`)
}