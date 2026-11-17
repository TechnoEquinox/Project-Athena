// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setCsrf } from './api'
import { listDeleted, restoreAppointment, restoreCall, restoreClient } from './restoreApi'

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

describe('restore API', () => {
  it.each([
    ['clients', 'deleted_clients'],
    ['appointments', 'deleted_appointments'],
    ['calls', 'deleted_calls'],
  ])('lists deleted %s', async (kind, key) => {
    fetchMock.mockReturnValue(reply(200, { retention_days: 30, [key]: [{ x: 1 }] }))
    expect(await listDeleted(kind)).toEqual({ retentionDays: 30, items: [{ x: 1 }] })
    expect(url()).toBe(`/api/admin/deleted-${kind}`)
  })

  it('refuses a kind it does not know', async () => {
    await expect(listDeleted('devices')).rejects.toThrow()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('restores a client without the force flag', async () => {
    fetchMock.mockReturnValue(reply(200, { client: { client_id: 5 }, restored: { devices: 1 } }))
    const data = await restoreClient(5)
    expect(data.restored).toEqual({ devices: 1 })
    expect(url()).toBe('/api/admin/clients/5/restore')
    expect(JSON.parse(options().body)).toEqual({})
  })

  it('restores a client with force over a duplicate', async () => {
    fetchMock.mockReturnValue(reply(200, { client: { client_id: 5 }, restored: {} }))
    await restoreClient(5, { force: true })
    expect(JSON.parse(options().body)).toEqual({ force: true })
  })

  it('restores an appointment and a call', async () => {
    fetchMock.mockReturnValue(reply(200, { appointment: { appointment_id: 7 } }))
    await restoreAppointment(7)
    expect(url()).toBe('/api/admin/appointments/7/restore')
    fetchMock.mockClear()
    fetchMock.mockReturnValue(reply(200, { call: { call_id: 4 } }))
    await restoreCall(4)
    expect(url()).toBe('/api/admin/calls/4/restore')
    expect(options().method).toBe('POST')
  })
})