// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setCsrf } from './api'
import { createTech, deactivateTech, listTechs, reactivateTech, updateTech } from './techsApi'

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

describe('techs API', () => {
  it('lists active techs by default', async () => {
    fetchMock.mockReturnValue(reply(200, { techs: [{ tech_id: 1 }] }))
    expect(await listTechs()).toEqual([{ tech_id: 1 }])
    expect(url()).toBe('/api/techs')
  })

  it('can include inactive techs', async () => {
    fetchMock.mockReturnValue(reply(200, { techs: [] }))
    await listTechs({ includeInactive: true })
    expect(url()).toBe('/api/techs?include_inactive=true')
  })

  it('creates without the force flag by default', async () => {
    fetchMock.mockReturnValue(reply(201, { tech: { tech_id: 5 } }))
    expect(await createTech({ first_name: 'Pat' })).toEqual({ tech_id: 5 })
    expect(url()).toBe('/api/admin/techs')
    expect(JSON.parse(options().body)).toEqual({ first_name: 'Pat' })
  })

  it('creates with force when the admin confirms a duplicate', async () => {
    fetchMock.mockReturnValue(reply(201, { tech: { tech_id: 5 } }))
    await createTech({ first_name: 'Pat' }, { force: true })
    expect(JSON.parse(options().body)).toEqual({ first_name: 'Pat', force: true })
  })

  it('updates with a PATCH', async () => {
    fetchMock.mockReturnValue(reply(200, { tech: { tech_id: 5 } }))
    await updateTech(5, { last_name: 'Lee' })
    expect(url()).toBe('/api/admin/techs/5')
    expect(options().method).toBe('PATCH')
  })

  it('deactivates and reports whether a login went inactive too', async () => {
    fetchMock.mockReturnValue(reply(200, { tech: { tech_id: 5 }, login_deactivated: true }))
    expect(await deactivateTech(5)).toEqual({ tech: { tech_id: 5 }, loginDeactivated: true })
    expect(options().method).toBe('DELETE')
  })

  it('reactivates', async () => {
    fetchMock.mockReturnValue(reply(200, { tech: { tech_id: 5, is_active: true } }))
    expect((await reactivateTech(5)).is_active).toBe(true)
    expect(url()).toBe('/api/admin/techs/5/reactivate')
    expect(options().method).toBe('POST')
  })
})