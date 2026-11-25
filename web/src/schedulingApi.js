// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { api } from './api'

const BASE = '/api/scheduling'

export async function listAvailability() {
  return (await api.get(`${BASE}/availability`)).availability
}

export async function saveAvailability(techId, data) {
  return (await api.put(`${BASE}/availability/${techId}`, data)).availability
}

export async function listNavigators() {
  return (await api.get(`${BASE}/navigators`)).navigators
}

export async function listSlots({ techId, date, excludeBookingId = null }) {
  const extra = excludeBookingId ? `&exclude_booking_id=${excludeBookingId}` : ''
  const { slots, blocked } = await api.get(`${BASE}/slots?tech_id=${techId}&date=${date}${extra}`)
  return { slots, blocked }
}

/** Calendar feed for a time range. Fixed parameter order. */
export async function listBookings({ from, to, techId = null }) {
  const params = [`from=${encodeURIComponent(from)}`, `to=${encodeURIComponent(to)}`]
  if (techId) params.push(`tech_id=${techId}`)
  return (await api.get(`${BASE}/bookings?${params.join('&')}`)).bookings
}

export async function getBooking(id) {
  return (await api.get(`${BASE}/bookings/${id}`)).booking
}

export async function createBooking(data) {
  return (await api.post(`${BASE}/bookings`, data)).booking
}

export async function updateBooking(id, data) {
  return (await api.patch(`${BASE}/bookings/${id}`, data)).booking
}

export function deleteBooking(id) {
  return api.delete(`${BASE}/bookings/${id}`)
}

// ---------- time off (blocked days) ----------

/** Blocks touching [from, to], both plain YYYY-MM-DD dates. Optionally only those that apply to one navigator. */
export async function listTimeOff({ from, to, techId = null }) {
  const extra = techId ? `&tech_id=${techId}` : ''
  return (await api.get(`${BASE}/time-off?from=${from}&to=${to}${extra}`)).time_off
}

/** Resolves to { time_off, affected_bookings }. */
export function createTimeOff(data) {
  return api.post(`${BASE}/time-off`, data)
}

export function updateTimeOff(id, data) {
  return api.put(`${BASE}/time-off/${id}`, data)
}

export function deleteTimeOff(id) {
  return api.delete(`${BASE}/time-off/${id}`)
}