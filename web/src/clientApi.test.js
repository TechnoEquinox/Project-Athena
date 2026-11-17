// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, setCsrf } from './api'
import {
  addDevice, createClient, deleteClient, getClient, listClients, removeDevice,
  updateClient, updateDevice,
} from './clientsApi'

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

describe('clients API', () => {
  it('lists with a query, limit and offset', async () => {
    fetchMock.mockReturnValue(reply(200, { clients: [], total: 0, limit: 25, offset: 0 }))
    await listClients({ q: 'ada', limit: 25, offset: 0 })
    expect(url()).toBe('/api/clients?q=ada&limit=25&offset=0')
  })

  it('leaves out an empty search', async () => {
    fetchMock.mockReturnValue(reply(200, { clients: [], total: 0, limit: 25, offset: 0 }))
    await listClients({ q: '', limit: 25, offset: 0 })
    expect(url()).toBe('/api/clients?limit=25&offset=0')
  })

  it('unwraps a single client', async () => {
    fetchMock.mockReturnValue(reply(200, { client: { client_id: 5 } }))
    expect(await getClient(5)).toEqual({ client_id: 5 })
    expect(url()).toBe('/api/clients/5')
  })

  it('creates without the force flag by default', async () => {
    fetchMock.mockReturnValue(reply(201, { client: { client_id: 1 } }))
    expect(await createClient({ first_name: 'A', last_name: 'B' })).toEqual({ client_id: 1 })
    expect(options().method).toBe('POST')
    expect(JSON.parse(options().body)).toEqual({ first_name: 'A', last_name: 'B' })
  })

  it('creates with force when the navigator confirms a duplicate', async () => {
    fetchMock.mockReturnValue(reply(201, { client: { client_id: 1 } }))
    await createClient({ first_name: 'A', last_name: 'B' }, { force: true })
    expect(JSON.parse(options().body)).toEqual({ first_name: 'A', last_name: 'B', force: true })
  })

  it('rejects a duplicate with the matches attached', async () => {
    fetchMock.mockReturnValue(reply(409, { error: 'possible_duplicate', matches: [{ client_id: 2 }] }))
    const err = await createClient({ first_name: 'A', last_name: 'B' }).catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.code).toBe('possible_duplicate')
    expect(err.body.matches).toHaveLength(1)
  })

  it('updates with a PATCH', async () => {
    fetchMock.mockReturnValue(reply(200, { client: { client_id: 5, email: null } }))
    await updateClient(5, { email: null })
    expect(url()).toBe('/api/clients/5')
    expect(options().method).toBe('PATCH')
    expect(JSON.parse(options().body)).toEqual({ email: null })
  })

  it('deletes and returns what was hidden with it', async () => {
    fetchMock.mockReturnValue(reply(200, { status: 'ok', deleted: { devices: 1, appointments: 2, call_logs: 0 } }))
    expect(await deleteClient(5)).toEqual({ devices: 1, appointments: 2, call_logs: 0 })
    expect(options().method).toBe('DELETE')
  })

  it('adds a device', async () => {
    fetchMock.mockReturnValue(reply(201, { device: { device_id: 9 } }))
    expect(await addDevice(5, { device_type: 'Phone' })).toEqual({ device_id: 9 })
    expect(url()).toBe('/api/clients/5/devices')
    expect(options().method).toBe('POST')
  })

  it('updates a device', async () => {
    fetchMock.mockReturnValue(reply(200, { device: { device_id: 9 } }))
    await updateDevice(5, 9, { description: 'x' })
    expect(url()).toBe('/api/clients/5/devices/9')
    expect(options().method).toBe('PATCH')
  })

  it('removes a device', async () => {
    fetchMock.mockReturnValue(reply(200, { status: 'ok' }))
    expect(await removeDevice(5, 9)).toBeUndefined()
    expect(url()).toBe('/api/clients/5/devices/9')
    expect(options().method).toBe('DELETE')
  })
})