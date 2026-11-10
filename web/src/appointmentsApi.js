import { api, qs } from './api'

const base = '/api/appointments'

export function listAppointments({ from, to, tech_id, location_id, client_id, limit, offset } = {}) {
  return api.get(`${base}${qs({ from, to, tech_id, location_id, client_id, limit, offset })}`)
}

export async function getAppointment(id) {
  return (await api.get(`${base}/${id}`)).appointment
}

export async function createAppointment(data) {
  return (await api.post(base, data)).appointment
}

export async function updateAppointment(id, data) {
  return (await api.patch(`${base}/${id}`, data)).appointment
}

export async function deleteAppointment(id) {
  await api.delete(`${base}/${id}`)
}