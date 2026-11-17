// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setCsrf } from './api'
import {
  createAppointment, deleteAppointment, getAppointment, listAppointments, updateAppointment,
} from './appointmentsApi'

function reply(status, body) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  })
}

let fetchMock
beforeEach(() => {
  fetchMock = vi.fn()
  globalThis.fetch = fetchMock
  setCsrf('tok')
})

const url = () => fetchMock.mock.calls[0][0]
const options = () => fetchMock.mock.calls[0][1]

describe('appointments API', () => {
  it('lists with every filter, in a fixed order', async () => {
    fetchMock.mockReturnValue(reply(200, { appointments: [], total: 0, limit: 25, offset: 0 }))
    await listAppointments({ from: 'a', to: 'b', tech_id: 2, location_id: 3, client_id: 5, limit: 25, offset: 0 })
    expect(url()).toBe('/api/appointments?from=a&to=b&tech_id=2&location_id=3&client_id=5&limit=25&offset=0')
  })

  it('leaves out empty filters', async () => {
    fetchMock.mockReturnValue(reply(200, { appointments: [], total: 0, limit: 10, offset: 0 }))
    await listAppointments({ tech_id: null, client_id: 5, limit: 10, offset: 0 })
    expect(url()).toBe('/api/appointments?client_id=5&limit=10&offset=0')
  })

  it('unwraps a single appointment', async () => {
    fetchMock.mockReturnValue(reply(200, { appointment: { appointment_id: 7 } }))
    expect(await getAppointment(7)).toEqual({ appointment_id: 7 })
    expect(url()).toBe('/api/appointments/7')
  })

  it('creates with a POST', async () => {
    fetchMock.mockReturnValue(reply(201, { appointment: { appointment_id: 1 } }))
    expect(await createAppointment({ client_id: 5 })).toEqual({ appointment_id: 1 })
    expect(options().method).toBe('POST')
    expect(JSON.parse(options().body)).toEqual({ client_id: 5 })
  })

  it('updates with a PATCH', async () => {
    fetchMock.mockReturnValue(reply(200, { appointment: { appointment_id: 7 } }))
    await updateAppointment(7, { length_minutes: 60 })
    expect(url()).toBe('/api/appointments/7')
    expect(options().method).toBe('PATCH')
  })

  it('deletes', async () => {
    fetchMock.mockReturnValue(reply(200, { status: 'ok' }))
    expect(await deleteAppointment(7)).toBeUndefined()
    expect(options().method).toBe('DELETE')
  })
})