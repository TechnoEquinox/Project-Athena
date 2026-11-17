// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setCsrf } from './api'
import {
  createUser, deactivateUser, listUsers, reactivateUser, resetPassword, resetTotp, unlockUser,
} from './usersApi'

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

describe('users API', () => {
  it('lists users', async () => {
    fetchMock.mockReturnValue(reply(200, { users: [{ user_id: 1 }] }))
    expect(await listUsers()).toEqual([{ user_id: 1 }])
    expect(url()).toBe('/api/admin/users')
  })

  it('creates a user', async () => {
    fetchMock.mockReturnValue(reply(201, { user: { user_id: 2 } }))
    expect(await createUser({ username: 'pat' })).toEqual({ user_id: 2 })
    expect(options().method).toBe('POST')
    expect(JSON.parse(options().body)).toEqual({ username: 'pat' })
  })

  it.each([
    ['deactivate', deactivateUser],
    ['reactivate', reactivateUser],
    ['unlock', unlockUser],
    ['reset-totp', resetTotp],
  ])('%s posts to the right place and returns the user', async (suffix, fn) => {
    fetchMock.mockReturnValue(reply(200, { user: { user_id: 4 } }))
    expect(await fn(4)).toEqual({ user_id: 4 })
    expect(url()).toBe(`/api/admin/users/4/${suffix}`)
    expect(options().method).toBe('POST')
  })

  it('resets a password', async () => {
    fetchMock.mockReturnValue(reply(200, { user: { user_id: 4 } }))
    await resetPassword(4, 'a brand new passphrase')
    expect(url()).toBe('/api/admin/users/4/reset-password')
    expect(JSON.parse(options().body)).toEqual({ new_password: 'a brand new passphrase' })
  })
})