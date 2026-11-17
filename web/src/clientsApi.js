// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { api, qs } from './api'

const base = '/api/clients'

export function listClients({ q, limit, offset } = {}) {
  return api.get(`${base}${qs({ q, limit, offset })}`)
}

export async function getClient(id) {
  return (await api.get(`${base}/${id}`)).client
}

export async function createClient(data, { force = false } = {}) {
  const body = force ? { ...data, force: true } : data
  return (await api.post(base, body)).client
}

export async function updateClient(id, data) {
  return (await api.patch(`${base}/${id}`, data)).client
}

export async function deleteClient(id) {
  return (await api.delete(`${base}/${id}`)).deleted
}

export async function addDevice(clientId, data) {
  return (await api.post(`${base}/${clientId}/devices`, data)).device
}

export async function updateDevice(clientId, deviceId, data) {
  return (await api.patch(`${base}/${clientId}/devices/${deviceId}`, data)).device
}

export async function removeDevice(clientId, deviceId) {
  await api.delete(`${base}/${clientId}/devices/${deviceId}`)
}