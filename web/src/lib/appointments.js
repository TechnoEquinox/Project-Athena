// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

export const clientLabel = (c) => `${c.last_name}, ${c.first_name}`

export function formatDateTime(iso) {
  return iso ? new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : ''
}

const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate())
const nextDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1)

/** January 1 to December 31 of the current year. */
export function yearRange(now = new Date()) {
  const year = now.getFullYear()
  return [new Date(year, 0, 1), new Date(year, 11, 31)]
}

/** A picked date range becomes from (inclusive) and to (exclusive), so the last day is fully included. */
export function rangeToParams(range) {
  if (!range || !range[0]) return {}
  const start = range[0]
  const end = range[1] ?? range[0]
  return { from: startOfDay(start).toISOString(), to: nextDay(end).toISOString() }
}

export const toApiTime = (date) => date.toISOString()

const sortedIds = (list) => [...new Set(list ?? [])].sort((a, b) => a - b)

export function emptyAppointmentForm(appt = null, { now = new Date(), client = null, techId = null } = {}) {
  if (appt) {
    return {
      client: { client_id: appt.client.client_id, label: clientLabel(appt.client) },
      when: new Date(appt.appointment_at),
      location_id: appt.location?.location_id ?? null,
      length_minutes: appt.length_minutes,
      notes: appt.notes ?? '',
      device_ids: (appt.devices ?? []).map((d) => d.device_id),
      tech_id: appt.tech.tech_id,
    }
  }
  return {
    client, when: new Date(now), location_id: null, length_minutes: null,
    notes: '', device_ids: [], tech_id: techId,
  }
}

/**
 * Create: the required fields plus whatever optional ones are filled in.
 * Edit: only the fields that changed. The tech is sent only when sendTech is true (admins).
 */
export function buildAppointmentPayload(form, original = null, { sendTech = false } = {}) {
  const notes = (form.notes ?? '').trim()
  const devices = sortedIds(form.device_ids)

  if (!original) {
    const out = {
      client_id: form.client.client_id,
      appointment_at: toApiTime(form.when),
      location_id: form.location_id,
      length_minutes: form.length_minutes,
    }
    if (notes) out.notes = notes
    if (devices.length) out.device_ids = devices
    if (sendTech && form.tech_id != null) out.tech_id = form.tech_id
    return out
  }

  const out = {}
  if (form.when.getTime() !== new Date(original.appointment_at).getTime()) {
    out.appointment_at = toApiTime(form.when)
  }
  if (form.location_id !== (original.location?.location_id ?? null)) out.location_id = form.location_id
  if (form.length_minutes !== original.length_minutes) out.length_minutes = form.length_minutes
  if ((notes || null) !== (original.notes ?? null)) out.notes = notes || null
  const before = sortedIds((original.devices ?? []).map((d) => d.device_id))
  if (JSON.stringify(devices) !== JSON.stringify(before)) out.device_ids = devices
  if (sendTech && form.tech_id !== original.tech.tech_id) out.tech_id = form.tech_id
  return out
}

const deviceLabel = (d) => (d.description ? `${d.device_type}: ${d.description}` : d.device_type)

/** The client's devices, plus any removed device already linked to this appointment. */
export function deviceOptions(devices = [], linked = []) {
  const byId = new Map(devices.map((d) => [d.device_id, { device_id: d.device_id, label: deviceLabel(d) }]))
  for (const d of linked) {
    if (!byId.has(d.device_id)) {
      byId.set(d.device_id, {
        device_id: d.device_id,
        label: deviceLabel(d) + (d.removed ? ' (removed)' : ''),
      })
    }
  }
  return [...byId.values()].sort((a, b) => a.device_id - b.device_id)
}

export function locationOptions(active = [], current = null) {
  const out = active.map((l) => ({ location_id: l.location_id, name: l.name }))
  if (current && !out.some((l) => l.location_id === current.location_id)) {
    out.push({ location_id: current.location_id, name: `${current.name} (no longer in use)` })
  }
  return out
}

const ROLE_LABELS = { admin: 'Admin', manager: 'Manager', navigator: 'Navigator' }

export function techLabel(t) {
  const role = t.login_role ? ` - ${ROLE_LABELS[t.login_role] ?? t.login_role}` : ''
  return `${t.last_name}, ${t.first_name}${role}${t.is_active === false ? ' (inactive)' : ''}`
}

export function techOptions(techs = [], current = null) {
  const out = techs.map((t) => ({ tech_id: t.tech_id, label: techLabel(t) }))
  if (current && !out.some((t) => t.tech_id === current.tech_id)) {
    out.push({ tech_id: current.tech_id, label: techLabel({ ...current, is_active: false }) })
  }
  return out
}