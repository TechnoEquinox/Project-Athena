// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setCsrf } from './api'
import {
  createLocation, deactivateLocation, listLocations, reactivateLocation, renameLocation,
} from './locationsApi'

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

describe('locations API', () => {
  it('lists active locations by default', async () => {
    fetchMock.mockReturnValue(reply(200, { locations: [{ location_id: 1 }] }))
    expect(await listLocations()).toEqual([{ location_id: 1 }])
    expect(url()).toBe('/api/locations')
  })

  it('can include removed locations', async () => {
    fetchMock.mockReturnValue(reply(200, { locations: [] }))
    await listLocations({ includeInactive: true })
    expect(url()).toBe('/api/locations?include_inactive=true')
  })

  it('creates a location', async () => {
    fetchMock.mockReturnValue(reply(201, { location: { location_id: 1, name: 'Library' } }))
    expect(await createLocation('Library')).toEqual({ location_id: 1, name: 'Library' })
    expect(url()).toBe('/api/admin/locations')
    expect(JSON.parse(options().body)).toEqual({ name: 'Library' })
  })

  it('renames with a PATCH', async () => {
    fetchMock.mockReturnValue(reply(200, { location: { location_id: 3 } }))
    await renameLocation(3, 'Senior Center')
    expect(url()).toBe('/api/admin/locations/3')
    expect(options().method).toBe('PATCH')
    expect(JSON.parse(options().body)).toEqual({ name: 'Senior Center' })
  })

  it('deactivates with a DELETE', async () => {
    fetchMock.mockReturnValue(reply(200, { location: { location_id: 3, is_active: false } }))
    expect((await deactivateLocation(3)).is_active).toBe(false)
    expect(url()).toBe('/api/admin/locations/3')
    expect(options().method).toBe('DELETE')
  })

  it('reactivates', async () => {
    fetchMock.mockReturnValue(reply(200, { location: { location_id: 3, is_active: true } }))
    await reactivateLocation(3)
    expect(url()).toBe('/api/admin/locations/3/reactivate')
    expect(options().method).toBe('POST')
  })
})